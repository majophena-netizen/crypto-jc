"""Signal pipeline: indicators -> AI confirmation -> DB -> optional trade."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app import ai, exchange, indicators
from app.config import settings
from app.db import Signal, Trade
from app.paper import paper_trader

logger = logging.getLogger(__name__)


@dataclass
class SignalResult:
    snapshot: indicators.IndicatorSnapshot
    verdict: ai.AIVerdict
    final_action: str
    explanation: str


def _combine(snap: indicators.IndicatorSnapshot, verdict: ai.AIVerdict) -> tuple[str, str]:
    """Combine technical + AI actions into a final decision.

    Rules:
    - If both agree (and not both hold), act.
    - If one is hold and the other has a concrete action with decent
      confidence, act on the concrete side.
    - Otherwise hold.
    """
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
    # Disagreement -> hold.
    return "hold", "technical and AI disagree"


async def scan(session: AsyncSession, execute_paper: bool = False) -> SignalResult:
    candles = await exchange.fetch_ohlcv()
    snap = indicators.compute(candles)
    verdict = await ai.analyse(snap)
    final, reason = _combine(snap, verdict)

    explanation = (
        f"RSI={snap.rsi:.1f} ({'oversold' if snap.rsi_vote == 1 else 'overbought' if snap.rsi_vote == -1 else 'neutral'}), "
        f"MACD {'bull' if snap.macd_vote == 1 else 'bear' if snap.macd_vote == -1 else 'flat'}, "
        f"MA {'up' if snap.ma_vote == 1 else 'down' if snap.ma_vote == -1 else 'sideways'}, "
        f"BB {'lower' if snap.bb_vote == 1 else 'upper' if snap.bb_vote == -1 else 'mid'}. "
        f"{reason}."
    )

    sig = Signal(
        symbol=settings.symbol,
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

    if execute_paper and final in {"buy", "sell"}:
        quote = settings.paper_starting_usdt * 0.1  # risk 10% of starting capital per trade
        try:
            trade = await paper_trader.execute(
                session,
                side=final,
                price=snap.price,
                quote_amount=quote,
                note=f"auto paper trade; {reason}",
            )
            if trade is None:
                logger.info("Paper trade skipped (insufficient funds or holdings)")
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Paper trade failed: %s", exc)

    await session.commit()
    return SignalResult(snapshot=snap, verdict=verdict, final_action=final, explanation=explanation)


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
