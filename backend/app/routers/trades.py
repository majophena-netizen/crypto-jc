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
from app.state import runtime

router = APIRouter(prefix="/api/trades", tags=["trades"])


class ManualTrade(BaseModel):
    side: str = Field(..., pattern="^(buy|sell)$")
    quote_amount: float = Field(..., gt=0)
    mode: str = Field(..., pattern="^(paper|live)$")
    symbol: str | None = None
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


@router.get("/closed")
async def list_closed_trades(
    limit: int = 50,
    mode: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Pair BUY + SELL trades per symbol (FIFO) and return completed round-trips.

    Each returned row has the full lifecycle on a single line: entry time/price,
    exit time/price, amount, duration, realized PnL in USDT + percent.
    """
    limit = max(1, min(500, limit))
    stmt = select(Trade).order_by(Trade.ts.asc())
    if mode:
        stmt = select(Trade).where(Trade.mode == mode).order_by(Trade.ts.asc())
    result = await session.execute(stmt)
    all_trades = list(result.scalars().all())

    # FIFO queue of open buy legs per (mode, symbol).
    from collections import deque

    open_legs: dict[tuple[str, str], deque[Trade]] = {}
    closed: list[dict] = []
    for t in all_trades:
        key = (t.mode, t.symbol)
        legs = open_legs.setdefault(key, deque())
        if t.side == "buy":
            legs.append(t)
            continue
        # side == "sell": pair with oldest buy legs until amount consumed.
        remaining = float(t.amount)
        sell_fee_left = float(t.fee or 0.0)
        exit_price = float(t.price)
        exit_ts = t.ts
        while remaining > 1e-12 and legs:
            buy = legs[0]
            take = min(remaining, float(buy.amount))
            buy_fee_share = (
                float(buy.fee or 0.0) * (take / float(buy.amount))
                if float(buy.amount) > 0 else 0.0
            )
            sell_fee_share = (
                sell_fee_left * (take / float(t.amount))
                if float(t.amount) > 0 else 0.0
            )
            entry_cost = take * float(buy.price)
            exit_value = take * exit_price
            pnl = exit_value - entry_cost - buy_fee_share - sell_fee_share
            pct = (pnl / entry_cost * 100.0) if entry_cost > 0 else 0.0
            duration_s = max(
                0, int((exit_ts - buy.ts).total_seconds())
            )
            closed.append({
                "mode": t.mode,
                "symbol": t.symbol,
                "amount": take,
                "entry_ts": buy.ts.isoformat(),
                "entry_price": float(buy.price),
                "exit_ts": exit_ts.isoformat(),
                "exit_price": exit_price,
                "quote_invested": entry_cost,
                "quote_returned": exit_value,
                "fees": buy_fee_share + sell_fee_share,
                "pnl": pnl,
                "pnl_pct": pct,
                "duration_seconds": duration_s,
                "entry_note": buy.note or "",
                "exit_note": t.note or "",
            })
            # Reduce or remove the buy leg.
            buy.amount = float(buy.amount) - take
            buy.fee = float(buy.fee or 0.0) - buy_fee_share
            if buy.amount <= 1e-12:
                legs.popleft()
            remaining -= take
        # Any leftover sell (no matching buy) is ignored.

    closed.sort(key=lambda r: r["exit_ts"], reverse=True)
    return {"closed": closed[:limit]}


@router.post("/execute")
async def execute(
    body: ManualTrade, session: AsyncSession = Depends(get_session)
) -> dict:
    sym = body.symbol or settings.symbol
    try:
        ticker = await exchange.fetch_ticker(symbol=sym)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"exchange error: {exc}") from exc
    price = float(ticker.get("last") or 0.0)
    if price <= 0:
        raise HTTPException(status_code=502, detail="invalid ticker price")

    if body.mode == "paper":
        trade = await paper_trader.execute(
            session, side=body.side, price=price, quote_amount=body.quote_amount,
            symbol=sym, note=body.note,
        )
        await session.commit()
    else:
        if not exchange.has_live_credentials():
            raise HTTPException(status_code=400, detail="live trading requires Binance API credentials")
        trade = await execute_live(
            session, side=body.side, price=price, quote_amount=body.quote_amount,
            symbol=sym, note=body.note,
        )
    if trade is None:
        raise HTTPException(status_code=400, detail="trade not executed (insufficient funds/holdings)")
    return trade_to_dict(trade)


@router.get("/portfolio")
async def portfolio(session: AsyncSession = Depends(get_session)) -> dict:
    # Use the most recent scan's mark prices; fall back to the primary ticker.
    mark_prices: dict[str, float] = dict(runtime.last_prices)
    try:
        ticker = await exchange.fetch_ticker()
        primary_price = float(ticker.get("last") or 0.0)
        if primary_price > 0:
            mark_prices.setdefault(settings.symbol, primary_price)
    except Exception:
        primary_price = mark_prices.get(settings.symbol, 0.0)

    # Rehydrate to ensure in-memory state matches DB.
    await paper_trader.rehydrate(session)
    positions = []
    unrealized = 0.0
    for pos in paper_trader.open_positions():
        mp = mark_prices.get(pos.symbol, pos.avg_cost)
        pnl = (mp - pos.avg_cost) * pos.amount
        unrealized += pnl
        positions.append({
            "symbol": pos.symbol,
            "amount": pos.amount,
            "avg_cost": pos.avg_cost,
            "mark_price": mp,
            "value_usdt": pos.amount * mp,
            "unrealized_pnl": pnl,
            "unrealized_pct": ((mp - pos.avg_cost) / pos.avg_cost * 100.0)
            if pos.avg_cost > 0 else 0.0,
        })
    paper = {
        "usdt": paper_trader.state.usdt,
        # Back-compat fields (primary symbol).
        "btc": paper_trader.state.btc,
        "avg_cost": paper_trader.state.avg_cost,
        "realized_pnl": paper_trader.state.realized_pnl,
        "mark_price": primary_price,
        "equity": paper_trader.equity(mark_prices),
        "unrealized_pnl": unrealized,
        "starting_usdt": settings.paper_starting_usdt,
        "positions": positions,
    }

    live: dict | None = None
    if exchange.has_live_credentials():
        live = await _live_snapshot(mark_prices, primary_price)

    return {"paper": paper, "live": live}


async def _live_snapshot(
    mark_prices: dict[str, float], primary_price: float
) -> dict:
    """Fetch Binance balances + value each non-USDT asset. Hard 10s timeout."""
    import asyncio as _asyncio
    try:
        bal = await _asyncio.wait_for(exchange.fetch_balance(), timeout=8.0)
    except Exception as exc:
        return {"error": str(exc), "testnet": exchange.is_testnet()}
    total = bal.get("total", {}) or {}
    usdt = float(total.get("USDT", 0.0) or 0.0)
    # Collect (symbol, asset, qty) for non-USDT non-zero balances.
    rows: list[tuple[str, str, float]] = []
    for asset, amt in total.items():
        try:
            qty = float(amt or 0.0)
        except (TypeError, ValueError):
            continue
        if qty <= 0 or asset == "USDT":
            continue
        rows.append((f"{asset}/USDT", asset, qty))

    # Fetch missing mark prices in parallel, with a short total timeout.
    missing = [sym for sym, _a, _q in rows if mark_prices.get(sym, 0.0) <= 0]
    async def _tk(sym: str) -> tuple[str, float]:
        try:
            t = await exchange.fetch_ticker(symbol=sym)
            return sym, float(t.get("last") or 0.0)
        except Exception:
            return sym, 0.0
    try:
        fetched = await _asyncio.wait_for(
            _asyncio.gather(*[_tk(s) for s in missing]), timeout=6.0
        )
        for sym, px in fetched:
            if px > 0:
                mark_prices[sym] = px
    except Exception:
        pass

    balances: list[dict] = []
    equity = usdt
    for sym, asset, qty in rows:
        mp = mark_prices.get(sym, 0.0)
        value = qty * mp
        equity += value
        balances.append({
            "symbol": sym, "asset": asset, "amount": qty,
            "mark_price": mp, "value_usdt": value,
        })
    return {
        "usdt": usdt,
        "btc": float(total.get("BTC", 0.0) or 0.0),
        "mark_price": primary_price,
        "equity": equity,
        "testnet": exchange.is_testnet(),
        "balances": balances,
    }


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
