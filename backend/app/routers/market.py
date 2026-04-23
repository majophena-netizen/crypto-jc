"""Public market data endpoints (no auth)."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import exchange, indicators
from app.config import settings
from app.db import Signal, get_session
from app.signals import signal_to_dict, snapshot_to_dict
from app.state import runtime

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/ticker")
async def ticker(symbol: str | None = None) -> dict:
    try:
        t = await exchange.fetch_ticker(symbol=symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"exchange error: {exc}") from exc
    return {
        "symbol": t.get("symbol"),
        "last": t.get("last"),
        "bid": t.get("bid"),
        "ask": t.get("ask"),
        "high": t.get("high"),
        "low": t.get("low"),
        "change_pct": t.get("percentage"),
        "quote_volume": t.get("quoteVolume"),
        "timestamp": t.get("timestamp"),
    }


@router.get("/candles")
async def candles(
    limit: int = 200, timeframe: str | None = None, symbol: str | None = None
) -> dict:
    limit = max(20, min(500, limit))
    try:
        data = await exchange.fetch_ohlcv(symbol=symbol, limit=limit, timeframe=timeframe)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"exchange error: {exc}") from exc
    return {
        "candles": [
            {
                "ts": c.ts,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in data
        ]
    }


@router.get("/indicators")
async def live_indicators(symbol: str | None = None) -> dict:
    try:
        data = await exchange.fetch_ohlcv(symbol=symbol)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"exchange error: {exc}") from exc
    snap = indicators.compute(data)
    return snapshot_to_dict(snap)


@router.get("/symbols")
async def symbols() -> dict:
    """Return the configured universe of symbols and current mark prices."""
    return {
        "primary": settings.symbol,
        "scan": settings.scan_symbols,
        "last_prices": runtime.last_prices,
    }


async def _latest_signal_for(session: AsyncSession, symbol: str) -> Signal | None:
    row = await session.execute(
        select(Signal).where(Signal.symbol == symbol).order_by(desc(Signal.ts)).limit(1)
    )
    return row.scalar_one_or_none()


@router.get("/scan")
async def market_scan() -> dict:
    """Latest per-symbol signal snapshot across the configured universe.

    Reads from the DB (most recent signal per symbol) so it does not trigger
    a scan itself. Returns pairs ranked by AI+technical conviction desc.
    """
    syms = settings.scan_symbols
    async with _session_factory() as session:
        rows = await asyncio.gather(
            *[_latest_signal_for(session, s) for s in syms]
        )
    out = []
    for sig in rows:
        if sig is None:
            continue
        d = signal_to_dict(sig)
        # Compute a conviction score identical to SignalResult.conviction.
        ai_sign = {"buy": 1.0, "sell": -1.0, "hold": 0.0}.get(sig.ai_action, 0.0)
        ai_w = ai_sign * max(0.0, min(1.0, sig.ai_confidence))
        d["conviction"] = 0.5 * sig.score + 0.5 * ai_w
        out.append(d)
    out.sort(key=lambda r: r["conviction"], reverse=True)
    return {"scan": out, "symbols": syms}


def _session_factory():  # pragma: no cover - thin wrapper
    # Defer import so module load order is safe.
    from app.db import SessionLocal
    return SessionLocal()


# Suppress unused-import warning (get_session is re-exported for other modules).
_ = get_session
