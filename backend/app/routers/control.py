"""Runtime control endpoints (mode switching, status)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import exchange
from app.config import settings
from app.state import runtime

router = APIRouter(prefix="/api/control", tags=["control"])


class ModeChange(BaseModel):
    mode: str = Field(..., pattern="^(signals|paper|live)$")


@router.get("/status")
async def status() -> dict:
    return {
        "mode": runtime.mode,
        "symbol": settings.symbol,
        "timeframe": settings.timeframe,
        "last_scan_at": runtime.last_scan_at.isoformat() if runtime.last_scan_at else None,
        "last_action": runtime.last_action,
        "last_price": runtime.last_price,
        "scan_interval_seconds": settings.scan_interval_seconds,
        "ai_enabled": settings.use_ai_confirmation and bool(settings.anthropic_api_key),
        "binance": {
            "has_credentials": exchange.has_live_credentials(),
            "testnet": exchange.is_testnet(),
        },
        "errors": runtime.errors[-5:],
    }


@router.post("/mode")
async def set_mode(body: ModeChange) -> dict:
    if body.mode == "live" and not exchange.has_live_credentials():
        raise HTTPException(
            status_code=400,
            detail="cannot switch to live mode without BINANCE_API_KEY and BINANCE_API_SECRET",
        )
    runtime.set_mode(body.mode)
    return {"mode": runtime.mode}
