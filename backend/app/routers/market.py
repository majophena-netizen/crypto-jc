"""Public market data endpoints (no auth)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import exchange, indicators
from app.signals import snapshot_to_dict

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/ticker")
async def ticker() -> dict:
    try:
        t = await exchange.fetch_ticker()
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
async def candles(limit: int = 200, timeframe: str | None = None) -> dict:
    limit = max(20, min(500, limit))
    try:
        data = await exchange.fetch_ohlcv(limit=limit, timeframe=timeframe)
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
async def live_indicators() -> dict:
    try:
        data = await exchange.fetch_ohlcv()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"exchange error: {exc}") from exc
    snap = indicators.compute(data)
    return snapshot_to_dict(snap)
