"""Trade endpoints: manual execution, history, portfolio."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import exchange
from app.config import settings
from app.db import Trade, get_session
from app.live import execute_live
from app.paper import paper_trader
from app.signals import trade_to_dict

router = APIRouter(prefix="/api/trades", tags=["trades"])


class ManualTrade(BaseModel):
    side: str = Field(..., pattern="^(buy|sell)$")
    quote_amount: float = Field(..., gt=0)
    mode: str = Field(..., pattern="^(paper|live)$")
    note: str = ""


@router.get("")
async def list_trades(
    limit: int = 100,
    mode: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    limit = max(1, min(1000, limit))
    stmt = select(Trade).order_by(Trade.ts.desc()).limit(limit)
    if mode:
        stmt = select(Trade).where(Trade.mode == mode).order_by(Trade.ts.desc()).limit(limit)
    result = await session.execute(stmt)
    return {"trades": [trade_to_dict(t) for t in result.scalars().all()]}


@router.post("/execute")
async def execute(
    body: ManualTrade, session: AsyncSession = Depends(get_session)
) -> dict:
    try:
        ticker = await exchange.fetch_ticker()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"exchange error: {exc}") from exc
    price = float(ticker.get("last") or 0.0)
    if price <= 0:
        raise HTTPException(status_code=502, detail="invalid ticker price")

    if body.mode == "paper":
        trade = await paper_trader.execute(
            session, side=body.side, price=price, quote_amount=body.quote_amount, note=body.note
        )
        await session.commit()
    else:
        if not exchange.has_live_credentials():
            raise HTTPException(status_code=400, detail="live trading requires Binance API credentials")
        trade = await execute_live(
            session, side=body.side, price=price, quote_amount=body.quote_amount, note=body.note
        )
    if trade is None:
        raise HTTPException(status_code=400, detail="trade not executed (insufficient funds/holdings)")
    return trade_to_dict(trade)


@router.get("/portfolio")
async def portfolio(session: AsyncSession = Depends(get_session)) -> dict:
    try:
        ticker = await exchange.fetch_ticker()
        price = float(ticker.get("last") or 0.0)
    except Exception:
        price = 0.0

    # Rehydrate to ensure in-memory state matches DB.
    await paper_trader.rehydrate(session)
    paper = {
        "usdt": paper_trader.state.usdt,
        "btc": paper_trader.state.btc,
        "avg_cost": paper_trader.state.avg_cost,
        "realized_pnl": paper_trader.state.realized_pnl,
        "mark_price": price,
        "equity": paper_trader.equity(price),
        "unrealized_pnl": (price - paper_trader.state.avg_cost) * paper_trader.state.btc
        if paper_trader.state.btc > 0
        else 0.0,
        "starting_usdt": settings.paper_starting_usdt,
    }

    live: dict | None = None
    if exchange.has_live_credentials():
        try:
            bal = await exchange.fetch_balance()
            total = bal.get("total", {}) or {}
            usdt = float(total.get("USDT", 0.0) or 0.0)
            btc = float(total.get("BTC", 0.0) or 0.0)
            live = {
                "usdt": usdt,
                "btc": btc,
                "mark_price": price,
                "equity": usdt + btc * price,
                "testnet": exchange.is_testnet(),
            }
        except Exception as exc:
            live = {"error": str(exc), "testnet": exchange.is_testnet()}

    return {"paper": paper, "live": live}


@router.get("/pnl/daily")
async def daily_pnl(days: int = 30, session: AsyncSession = Depends(get_session)) -> dict:
    days = max(1, min(365, days))
    since = datetime.now(UTC) - timedelta(days=days)
    result = await session.execute(
        select(Trade).where(Trade.ts >= since).order_by(Trade.ts.asc())
    )
    buckets: dict[str, dict[str, float]] = {}
    today = date.today()
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        buckets[d] = {"paper": 0.0, "live": 0.0, "trades": 0}
    for tr in result.scalars().all():
        day = tr.ts.date().isoformat()
        if day not in buckets:
            buckets[day] = {"paper": 0.0, "live": 0.0, "trades": 0}
        buckets[day][tr.mode] = buckets[day].get(tr.mode, 0.0) + tr.pnl
        buckets[day]["trades"] = buckets[day].get("trades", 0) + 1
    series = [
        {"date": d, "paper": v["paper"], "live": v["live"], "trades": int(v["trades"])}
        for d, v in sorted(buckets.items())
    ]
    return {"days": series}


@router.post("/paper/reset")
async def reset_paper(session: AsyncSession = Depends(get_session)) -> dict:
    # Wipe paper trades then reset wallet.
    await session.execute(Trade.__table__.delete().where(Trade.mode == "paper"))
    await session.commit()
    paper_trader.reset()
    return {"ok": True, "state": {
        "usdt": paper_trader.state.usdt,
        "btc": paper_trader.state.btc,
        "avg_cost": paper_trader.state.avg_cost,
        "realized_pnl": paper_trader.state.realized_pnl,
    }}
