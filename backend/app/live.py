"""Live trading executor (Binance testnet by default)."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app import exchange
from app.config import settings
from app.db import Trade

logger = logging.getLogger(__name__)


async def execute_live(
    session: AsyncSession,
    side: str,
    price: float,
    quote_amount: float,
    symbol: str | None = None,
    note: str = "",
) -> Trade | None:
    """Submit a market order on Binance and record the trade.

    ``quote_amount`` is in USDT; amount (base asset) is derived from price.
    Orders are capped by ``LIVE_MAX_ORDER_USDT`` as a hard safety guard.
    """
    if side not in {"buy", "sell"}:
        raise ValueError(f"invalid side: {side}")
    if not exchange.has_live_credentials():
        raise RuntimeError("Live trading requires BINANCE_API_KEY and BINANCE_API_SECRET")

    sym = symbol or settings.symbol
    quote_amount = min(quote_amount, settings.live_max_order_usdt)
    if quote_amount <= 0 or price <= 0:
        return None
    amount = round(quote_amount / price, 6)
    if amount <= 0:
        return None

    order = await exchange.create_market_order(side, amount, symbol=sym)
    filled_price = float(order.get("average") or order.get("price") or price)
    filled_amount = float(order.get("filled") or amount)
    fee_cost = 0.0
    for fee in order.get("fees") or []:
        try:
            fee_cost += float(fee.get("cost") or 0.0)
        except (TypeError, ValueError):
            pass
    external_id = str(order.get("id") or "")

    trade = Trade(
        mode="live",
        symbol=sym,
        side=side,
        price=filled_price,
        amount=filled_amount,
        quote_amount=filled_price * filled_amount,
        fee=fee_cost,
        pnl=0.0,  # broker-reported PnL isn't computed here; use Binance statements
        external_id=external_id,
        note=note + (" [TESTNET]" if exchange.is_testnet() else " [MAINNET]"),
    )
    session.add(trade)
    await session.flush()
    await session.commit()
    return trade
