"""Runtime control endpoints (mode switching, status)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import autotrader, exchange
from app.config import settings
from app.state import runtime

router = APIRouter(prefix="/api/control", tags=["control"])


class ModeChange(BaseModel):
    mode: str = Field(..., pattern="^(signals|paper|live)$")


class AutoConfig(BaseModel):
    auto_trade_enabled: bool | None = None
    entry_position_usdt: float | None = Field(default=None, gt=0)
    take_profit_pct: float | None = Field(default=None, gt=0)
    stop_loss_pct: float | None = Field(default=None, gt=0)
    min_ai_confidence: float | None = Field(default=None, ge=0, le=1)
    auto_trade_cooldown_seconds: int | None = Field(default=None, ge=0)
    max_concurrent_positions: int | None = Field(default=None, ge=1, le=20)
    scan_symbols: str | None = None  # CSV list
    trailing_stop_pct: float | None = Field(default=None, ge=0)
    trailing_arm_pct: float | None = Field(default=None, ge=0)
    max_hold_hours: float | None = Field(default=None, ge=0)


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
        "ai_enabled": settings.use_ai_confirmation and bool(settings.active_ai_provider),
        "ai_provider": settings.active_ai_provider or None,
        "binance": {
            "has_credentials": exchange.has_live_credentials(),
            "testnet": exchange.is_testnet(),
        },
        "scan_symbols": settings.scan_symbols,
        "autotrader": {
            "enabled": settings.auto_trade_enabled,
            "entry_position_usdt": settings.entry_position_usdt,
            "take_profit_pct": settings.take_profit_pct,
            "stop_loss_pct": settings.stop_loss_pct,
            "min_ai_confidence": settings.min_ai_confidence,
            "cooldown_seconds": settings.auto_trade_cooldown_seconds,
            "max_concurrent_positions": settings.max_concurrent_positions,
            "trailing_stop_pct": settings.trailing_stop_pct,
            "trailing_arm_pct": settings.trailing_arm_pct,
            "max_hold_hours": settings.max_hold_hours,
            "scan_symbols": settings.scan_symbols,
            "last_trade_at": (
                autotrader.state.last_trade_at.isoformat()
                if autotrader.state.last_trade_at else None
            ),
            "recent_decisions": autotrader.state.last_decisions[-10:],
        },
        "errors": runtime.errors[-5:],
    }


@router.post("/autotrader")
async def update_autotrader(body: AutoConfig) -> dict:
    """Update auto-trading parameters at runtime (in-memory; not persisted)."""
    if body.auto_trade_enabled is not None:
        settings.auto_trade_enabled = body.auto_trade_enabled
    if body.entry_position_usdt is not None:
        settings.entry_position_usdt = body.entry_position_usdt
    if body.take_profit_pct is not None:
        settings.take_profit_pct = body.take_profit_pct
    if body.stop_loss_pct is not None:
        settings.stop_loss_pct = body.stop_loss_pct
    if body.min_ai_confidence is not None:
        settings.min_ai_confidence = body.min_ai_confidence
    if body.auto_trade_cooldown_seconds is not None:
        settings.auto_trade_cooldown_seconds = body.auto_trade_cooldown_seconds
    if body.max_concurrent_positions is not None:
        settings.max_concurrent_positions = body.max_concurrent_positions
    if body.scan_symbols is not None:
        settings.scan_symbols_csv = body.scan_symbols
    if body.trailing_stop_pct is not None:
        settings.trailing_stop_pct = body.trailing_stop_pct
    if body.trailing_arm_pct is not None:
        settings.trailing_arm_pct = body.trailing_arm_pct
    if body.max_hold_hours is not None:
        settings.max_hold_hours = body.max_hold_hours
    return {
        "enabled": settings.auto_trade_enabled,
        "entry_position_usdt": settings.entry_position_usdt,
        "take_profit_pct": settings.take_profit_pct,
        "stop_loss_pct": settings.stop_loss_pct,
        "min_ai_confidence": settings.min_ai_confidence,
        "cooldown_seconds": settings.auto_trade_cooldown_seconds,
        "max_concurrent_positions": settings.max_concurrent_positions,
        "trailing_stop_pct": settings.trailing_stop_pct,
        "trailing_arm_pct": settings.trailing_arm_pct,
        "max_hold_hours": settings.max_hold_hours,
        "scan_symbols": settings.scan_symbols,
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
