"""Signal endpoints: manual scan + history."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Signal, get_session
from app.signals import scan, signal_to_dict
from app.state import runtime

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.post("/scan")
async def manual_scan(session: AsyncSession = Depends(get_session)) -> dict:
    execute_paper = runtime.mode == "paper"
    result = await scan(session, execute_paper=execute_paper)
    runtime.mark_scan(result.snapshot.price, result.final_action)
    return {
        "action": result.final_action,
        "explanation": result.explanation,
        "snapshot": {
            "price": result.snapshot.price,
            "rsi": result.snapshot.rsi,
            "macd": result.snapshot.macd,
            "macd_signal": result.snapshot.macd_signal,
            "ma_fast": result.snapshot.ma_fast,
            "ma_slow": result.snapshot.ma_slow,
            "bb_upper": result.snapshot.bb_upper,
            "bb_mid": result.snapshot.bb_mid,
            "bb_lower": result.snapshot.bb_lower,
            "score": result.snapshot.score,
            "technical_action": result.snapshot.action,
        },
        "ai": {
            "action": result.verdict.action,
            "confidence": result.verdict.confidence,
            "rationale": result.verdict.rationale,
        },
    }


@router.get("")
async def list_signals(limit: int = 50, session: AsyncSession = Depends(get_session)) -> dict:
    limit = max(1, min(500, limit))
    result = await session.execute(
        select(Signal).order_by(Signal.ts.desc()).limit(limit)
    )
    return {"signals": [signal_to_dict(s) for s in result.scalars().all()]}
