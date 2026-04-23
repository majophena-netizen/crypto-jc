"""AI confirmation for trading signals (Gemini or Claude).

Given an indicator snapshot, ask the configured LLM to classify the setup as
buy / sell / hold and produce a short rationale. The AI vote is combined
with the technical score to produce the final action.

Provider is chosen automatically based on which API key is present:
- ``GEMINI_API_KEY`` / ``GEMINI_API`` → Google Gemini (free tier)
- ``ANTHROPIC_API_KEY`` → Anthropic Claude

Set ``AI_PROVIDER=gemini`` or ``AI_PROVIDER=anthropic`` to force one.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

import httpx
from anthropic import Anthropic

from app.config import settings
from app.indicators import IndicatorSnapshot

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a disciplined crypto trading analyst. You receive a snapshot of "
    "technical indicators for a BTC/USDT chart and must output a single JSON "
    "object with exactly these keys: action (one of buy, sell, hold), "
    "confidence (float in [0,1]), rationale (one or two short sentences). "
    "Be conservative: prefer hold when signals conflict or confidence is low. "
    "Never output anything except the JSON object."
)


@dataclass
class AIVerdict:
    action: str
    confidence: float
    rationale: str


def _build_user_prompt(snap: IndicatorSnapshot) -> str:
    payload = {
        "symbol": settings.symbol,
        "timeframe": settings.timeframe,
        "price": round(snap.price, 2),
        "rsi": round(snap.rsi, 2),
        "rsi_thresholds": {"oversold": settings.rsi_oversold, "overbought": settings.rsi_overbought},
        "macd": round(snap.macd, 4),
        "macd_signal": round(snap.macd_signal, 4),
        "macd_hist": round(snap.macd_hist, 4),
        "ma_fast": round(snap.ma_fast, 2),
        "ma_slow": round(snap.ma_slow, 2),
        "bb_upper": round(snap.bb_upper, 2),
        "bb_mid": round(snap.bb_mid, 2),
        "bb_lower": round(snap.bb_lower, 2),
        "technical_votes": {
            "rsi": snap.rsi_vote,
            "macd": snap.macd_vote,
            "ma": snap.ma_vote,
            "bollinger": snap.bb_vote,
        },
        "technical_action": snap.action,
        "technical_score": round(snap.score, 3),
    }
    return (
        "Here is the latest indicator snapshot:\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```\n"
        "Respond with the JSON verdict object now."
    )


def _fallback(snap: IndicatorSnapshot, note: str = "") -> AIVerdict:
    return AIVerdict(
        action=snap.action,
        confidence=abs(snap.score),
        rationale=(note or "AI disabled; using technical consensus only."),
    )


def _parse_verdict(raw: str, snap: IndicatorSnapshot) -> AIVerdict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    # Handle models that return prose before/after the JSON.
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        text = text[first : last + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Could not parse AI response: %s", raw)
        return _fallback(snap, "AI returned non-JSON; using technical consensus.")

    action = str(data.get("action", "hold")).lower()
    if action not in {"buy", "sell", "hold"}:
        action = "hold"
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    rationale = str(data.get("rationale", "")).strip()[:500]
    return AIVerdict(action=action, confidence=confidence, rationale=rationale)


def _call_anthropic(prompt: str) -> str:
    client = Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=300,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    chunks: list[str] = []
    for block in message.content:
        if getattr(block, "type", None) == "text":
            chunks.append(block.text)
    return "".join(chunks).strip()


def _gemini_once(prompt: str, model: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent"
    )
    body = {
        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 300,
            "responseMimeType": "application/json",
        },
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            url,
            headers={"x-goog-api-key": settings.gemini_api_key},
            json=body,
        )
        r.raise_for_status()
        data = r.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"gemini empty response: {data}")
    parts = candidates[0].get("content", {}).get("parts", []) or []
    return "".join(p.get("text", "") for p in parts).strip()


def _call_gemini(prompt: str) -> str:
    """Try the primary model, fall back to ``gemini_fallback_model`` on 5xx."""
    models = [settings.gemini_model]
    if settings.gemini_fallback_model and settings.gemini_fallback_model != settings.gemini_model:
        models.append(settings.gemini_fallback_model)
    last_exc: Exception | None = None
    for m in models:
        try:
            return _gemini_once(prompt, m)
        except httpx.HTTPStatusError as e:
            last_exc = e
            if e.response.status_code in {429, 500, 502, 503, 504}:
                logger.warning("gemini %s unavailable (%s), trying next model", m, e.response.status_code)
                continue
            raise
    raise last_exc if last_exc else RuntimeError("gemini: no models available")


async def analyse(snap: IndicatorSnapshot) -> AIVerdict:
    """Ask the configured LLM for a verdict. Falls back to the technical action on error."""

    if not settings.use_ai_confirmation:
        return _fallback(snap)

    provider = settings.active_ai_provider
    if not provider:
        return _fallback(snap)

    prompt = _build_user_prompt(snap)

    def _call() -> str:
        if provider == "gemini":
            return _call_gemini(prompt)
        return _call_anthropic(prompt)

    try:
        raw = await asyncio.to_thread(_call)
    except Exception as exc:  # pragma: no cover - network
        logger.warning("%s call failed: %s", provider, exc)
        return _fallback(snap, f"AI error ({provider}): {exc}")

    return _parse_verdict(raw, snap)
