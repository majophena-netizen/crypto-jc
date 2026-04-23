"""Signal pipeline: indicators -> AI confirmation -> DB.

Supports per-symbol scans and a parallel multi-symbol scanner. To stay under
free-tier AI rate limits we compute indicators in parallel but call the AI
sequentially with a small gap between calls.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, exchange, indicators
from app.config import settings
from app.db import Signal, Trade

logger = logging.getLogger(__name__)

# Gemini free tier is throttled (10 RPM + 1000 RPD for -lite). Two mitigations:
# 1. Sequential AI calls with a gap.
# 2. Per-symbol cache with TTL so most scans reuse a recent verdict.
# 3. Skip AI entirely for technically-neutral symbols (|score| < threshold).
_AI_GAP_SECONDS = 6.0
_AI_CACHE_TTL_SECONDS = 300  # 5 min
_AI_SKIP_SCORE_THRESHOLD = 0.25

# symbol -> (timestamp, verdict, snapshot_score)
_ai_cache: dict[str, tuple[float, ai.AIVerdict]] = {}


@dataclass
class SignalResult:
    symbol: str
    snapshot: indicators.IndicatorSnapshot
    verdict: ai.AIVerdict
    final_action: str
    explanation: str

    @property
    def conviction(self) -> float:
        tech = self.snapshot.score
        ai_sign = {"buy": 1.0, "sell": -1.0, "hold": 0.0}.get(self.verdict.action, 0.0)
        ai_w = ai_sign * max(0.0, min(1.0, self.verdict.confidence))
        return 0.5 * tech + 0.5 * ai_w


def _combine(snap: indicators.IndicatorSnapshot, verdict: ai.AIVerdict) -> tuple[str, str]:
    tech = snap.action
    ai_act = verdict.action

    if tech == ai_act and tech != "hold":
        return tech, f"technical and AI both recommend {tech}"
    if tech != "hold" and ai_act == "hold":
        if abs(snap.score) >= 0.75:
            return tech, f"strong technical score ({snap.score:+.2f}); AI neutral"
        return "hold", "technical signal not confirmed by AI"
    if tech == "hold" and ai_act != "hold":
        if verdict.confidence >= 0.7:
            return ai_act, f"AI high-confidence {ai_act} ({verdict.confidence:.2f}); technicals neutral"
        return "hold", "AI signal not confirmed by technicals"
    return "hold", "technical and AI disagree"


def _explanation(snap: indicators.IndicatorSnapshot, reason: str) -> str:
    return (
        f"RSI={snap.rsi:.1f} ({'oversold' if snap.rsi_vote == 1 else 'overbought' if snap.rsi_vote == -1 else 'neutral'}), "
        f"MACD {'bull' if snap.macd_vote == 1 else 'bear' if snap.macd_vote == -1 else 'flat'}, "
        f"MA {'up' if snap.ma_vote == 1 else 'down' if snap.ma_vote == -1 else 'sideways'}, "
        f"BB {'lower' if snap.bb_vote == 1 else 'upper' if snap.bb_vote == -1 else 'mid'}. "
        f"{reason}."
    )


async def _compute_snapshot(symbol: str) -> indicators.IndicatorSnapshot | None:
    try:
        candles = await exchange.fetch_ohlcv(symbol=symbol)
        return indicators.compute(candles)
    except Exception as exc:
        logger.warning("candles(%s) failed: %s", symbol, exc)
        return None


async def _persist(
    session: AsyncSession,
    symbol: str,
    snap: indicators.IndicatorSnapshot,
    verdict: ai.AIVerdict,
) -> SignalResult:
    final, reason = _combine(snap, verdict)
    explanation = _explanation(snap, reason)
    sig = Signal(
        symbol=symbol,
        timeframe=settings.timeframe,
        price=snap.price,
        action=final,
        score=snap.score,
        rsi=snap.rsi,
        macd=snap.macd,
        macd_signal=snap.macd_signal,
        ma_fast=snap.ma_fast,
        ma_slow=snap.ma_slow,
        ai_action=verdict.action,
        ai_confidence=verdict.confidence,
        ai_rationale=verdict.rationale,
        explanation=explanation,
    )
    session.add(sig)
    await session.flush()
    return SignalResult(
        symbol=symbol, snapshot=snap, verdict=verdict,
        final_action=final, explanation=explanation,
    )


async def scan_symbol(session: AsyncSession, symbol: str) -> SignalResult:
    """Run the full signal pipeline for a single symbol and persist it."""
    snap = await _compute_snapshot(symbol)
    if snap is None:
        raise RuntimeError(f"no candles for {symbol}")
    verdict = await ai.analyse(snap)
    return await _persist(session, symbol, snap, verdict)


async def scan(session: AsyncSession, execute_paper: bool = False) -> SignalResult:
    """Single-symbol scan for the primary symbol (back-compat)."""
    _ = execute_paper
    res = await scan_symbol(session, settings.symbol)
    await session.commit()
    return res


def _neutral_verdict(reason: str = "AI skipped (tech neutral)") -> ai.AIVerdict:
    return ai.AIVerdict(action="hold", confidence=0.0, rationale=reason)


async def _get_or_fetch_verdict(
    symbol: str,
    snap: indicators.IndicatorSnapshot,
    ai_enabled: bool,
    need_gap: bool,
) -> tuple[ai.AIVerdict, bool]:
    """Return the AI verdict for (symbol, snap). Second element = True if
    we actually made a fresh AI call (caller should sleep after)."""
    now = time.monotonic()
    # Skip AI for pairs with weak technical signal — they are not trade candidates.
    if abs(snap.score) < _AI_SKIP_SCORE_THRESHOLD:
        cached = _ai_cache.get(symbol)
        if cached and now - cached[0] < _AI_CACHE_TTL_SECONDS:
            return cached[1], False
        return _neutral_verdict(), False
    # Cache hit?
    cached = _ai_cache.get(symbol)
    if cached and now - cached[0] < _AI_CACHE_TTL_SECONDS:
        return cached[1], False
    if not ai_enabled:
        return _neutral_verdict("AI disabled"), False
    if need_gap:
        await asyncio.sleep(_AI_GAP_SECONDS)
    verdict = await ai.analyse(snap)
    _ai_cache[symbol] = (now, verdict)
    return verdict, True


async def scan_all(
    session: AsyncSession, symbols: list[str] | None = None
) -> list[SignalResult]:
    """Scan many symbols. Indicators run in parallel; AI is serialized and
    cached to respect free-tier rate limits.

    Returns the list ranked by conviction desc.
    """
    syms = symbols or settings.scan_symbols

    # Phase 1: parallel indicator computation.
    raw = await asyncio.gather(*[_compute_snapshot(s) for s in syms])
    snaps: list[tuple[str, indicators.IndicatorSnapshot]] = [
        (s, snap) for s, snap in zip(syms, raw, strict=False) if snap is not None
    ]

    # Phase 2: AI verdicts (cached / serialized).
    ai_enabled = bool(settings.active_ai_provider) and settings.use_ai_confirmation
    results: list[SignalResult] = []
    did_ai_call = False
    for sym, snap in snaps:
        try:
            verdict, fresh = await _get_or_fetch_verdict(
                sym, snap, ai_enabled, need_gap=did_ai_call
            )
            if fresh:
                did_ai_call = True
            r = await _persist(session, sym, snap, verdict)
            results.append(r)
        except Exception as exc:
            logger.warning("scan_symbol(%s) failed: %s", sym, exc)
            continue

    await session.commit()
    results.sort(key=lambda r: r.conviction, reverse=True)
    return results


def snapshot_to_dict(snap: indicators.IndicatorSnapshot) -> dict:
    return asdict(snap)


def trade_to_dict(trade: Trade) -> dict:
    return {
        "id": trade.id,
        "ts": trade.ts.isoformat(),
        "mode": trade.mode,
        "symbol": trade.symbol,
        "side": trade.side,
        "price": trade.price,
        "amount": trade.amount,
        "quote_amount": trade.quote_amount,
        "fee": trade.fee,
        "pnl": trade.pnl,
        "note": trade.note,
    }


def signal_to_dict(sig: Signal) -> dict:
    return {
        "id": sig.id,
        "ts": sig.ts.isoformat(),
        "symbol": sig.symbol,
        "timeframe": sig.timeframe,
        "price": sig.price,
        "action": sig.action,
        "score": sig.score,
        "rsi": sig.rsi,
        "macd": sig.macd,
        "macd_signal": sig.macd_signal,
        "ma_fast": sig.ma_fast,
        "ma_slow": sig.ma_slow,
        "ai_action": sig.ai_action,
        "ai_confidence": sig.ai_confidence,
        "ai_rationale": sig.ai_rationale,
        "explanation": sig.explanation,
    }


def signal_result_to_dict(res: SignalResult) -> dict:
    snap = res.snapshot
    return {
        "symbol": res.symbol,
        "price": snap.price,
        "action": res.final_action,
        "score": snap.score,
        "conviction": res.conviction,
        "rsi": snap.rsi,
        "macd": snap.macd,
        "macd_signal": snap.macd_signal,
        "ma_fast": snap.ma_fast,
        "ma_slow": snap.ma_slow,
        "bb_upper": snap.bb_upper,
        "bb_lower": snap.bb_lower,
        "ai_action": res.verdict.action,
        "ai_confidence": res.verdict.confidence,
        "ai_rationale": res.verdict.rationale,
        "explanation": res.explanation,
    }
