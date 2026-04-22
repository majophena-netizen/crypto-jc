"""Claude-powered AI confirmation for trading signals.

Given an indicator snapshot, ask Claude to classify the setup as
buy / sell / hold and produce a short rationale. The AI vote is combined
with the technical score to produce the final action.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

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


def _client() -> Anthropic | None:
    if not settings.anthropic_api_key:
        return None
    return Anthropic(api_key=settings.anthropic_api_key)


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


async def analyse(snap: IndicatorSnapshot) -> AIVerdict:
    """Ask Claude for a verdict. Falls back to the technical action on error."""

    client = _client()
    if client is None or not settings.use_ai_confirmation:
        return _fallback(snap)

    prompt = _build_user_prompt(snap)

    def _call() -> str:
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

    try:
        raw = await asyncio.to_thread(_call)
    except Exception as exc:  # pragma: no cover - network
        logger.warning("Claude call failed: %s", exc)
        return _fallback(snap, f"AI error: {exc}")

    text = raw
    if text.startswith("```"):
        # Strip ```json ... ``` fences if Claude wrapped the payload.
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Could not parse Claude response: %s", raw)
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
