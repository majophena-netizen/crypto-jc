"""Signal endpoints: manual scan + history."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import Signal, get_session
from app.signals import scan_all, signal_result_to_dict, signal_to_dict
from app.state import runtime

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.post("/scan")
async def manual_scan(session: AsyncSession = Depends(get_session)) -> dict:
    """Trigger a multi-pair scan and return ranked results."""
    results = await scan_all(session, settings.scan_symbols)
    if results:
        runtime.last_prices = {r.symbol: r.snapshot.price for r in results}
        primary = next(
            (r for r in results if r.symbol == settings.symbol), results[0]
        )
        runtime.mark_scan(primary.snapshot.price, primary.final_action)
    ranked = [signal_result_to_dict(r) for r in results]
    primary_payload = None
    if results:
        p = next((r for r in results if r.symbol == settings.symbol), results[0])
        primary_payload = {
            "symbol": p.symbol,
            "action": p.final_action,
            "explanation": p.explanation,
            "snapshot": {
                "price": p.snapshot.price,
                "rsi": p.snapshot.rsi,
                "macd": p.snapshot.macd,
                "macd_signal": p.snapshot.macd_signal,
                "ma_fast": p.snapshot.ma_fast,
                "ma_slow": p.snapshot.ma_slow,
                "bb_upper": p.snapshot.bb_upper,
                "bb_mid": p.snapshot.bb_mid,
                "bb_lower": p.snapshot.bb_lower,
                "score": p.snapshot.score,
                "technical_action": p.snapshot.action,
            },
            "ai": {
                "action": p.verdict.action,
                "confidence": p.verdict.confidence,
                "rationale": p.verdict.rationale,
            },
        }
    return {"primary": primary_payload, "scan": ranked}


@router.get("")
async def list_signals(
    limit: int = 50,
    symbol: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    limit = max(1, min(500, limit))
    stmt = select(Signal).order_by(Signal.ts.desc()).limit(limit)
    if symbol:
        stmt = (
            select(Signal)
            .where(Signal.symbol == symbol)
            .order_by(Signal.ts.desc())
            .limit(limit)
        )
    result = await session.execute(stmt)
    return {"signals": [signal_to_dict(s) for s in result.scalars().all()]}
