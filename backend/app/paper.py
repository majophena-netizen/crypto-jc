"""In-memory paper trading engine backed by persistent trades in the DB.

Supports multiple concurrent positions across symbols. A single USDT cash
balance is shared, while each symbol has its own base-asset position and
average cost. State is rebuilt from the DB on startup by replaying every
``mode='paper'`` trade in order.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import Trade

logger = logging.getLogger(__name__)


@dataclass
class PaperPosition:
    symbol: str
    amount: float = 0.0  # base asset amount (e.g. BTC, ETH)
    avg_cost: float = 0.0  # average USDT cost per unit


@dataclass
class PaperState:
    usdt: float
    positions: dict[str, PaperPosition] = field(default_factory=dict)
    realized_pnl: float = 0.0

    # -- Back-compat helpers for callers that still think in terms of a
    #    single BTC position. They reflect the primary symbol in settings.
    @property
    def btc(self) -> float:
        pos = self.positions.get(settings.symbol)
        return pos.amount if pos else 0.0

    @property
    def avg_cost(self) -> float:
        pos = self.positions.get(settings.symbol)
        return pos.avg_cost if pos else 0.0


class PaperTrader:
    """Multi-symbol paper trading bookkeeper.

    State is rebuilt from the DB on startup so restarts don't lose the
    virtual portfolio.
    """

    def __init__(self) -> None:
        self.state = PaperState(usdt=settings.paper_starting_usdt)

    async def rehydrate(self, session: AsyncSession) -> None:
        self.state = PaperState(usdt=settings.paper_starting_usdt)
        result = await session.execute(
            select(Trade).where(Trade.mode == "paper").order_by(Trade.ts.asc())
        )
        for tr in result.scalars().all():
            self._apply(tr.symbol, tr.side, tr.price, tr.amount, tr.fee)

    def reset(self) -> PaperState:
        self.state = PaperState(usdt=settings.paper_starting_usdt)
        return self.state

    def position(self, symbol: str) -> PaperPosition:
        pos = self.state.positions.get(symbol)
        if pos is None:
            pos = PaperPosition(symbol=symbol)
            self.state.positions[symbol] = pos
        return pos

    def open_positions(self) -> list[PaperPosition]:
        return [p for p in self.state.positions.values() if p.amount > 1e-12]

    def _apply(
        self, symbol: str, side: str, price: float, amount: float, fee: float
    ) -> float:
        """Apply a fill to state, returning realized PnL for sells."""
        pos = self.position(symbol)
        pnl = 0.0
        if side == "buy":
            cost = price * amount
            total = cost + fee
            new_amt = pos.amount + amount
            if new_amt > 0:
                pos.avg_cost = (pos.avg_cost * pos.amount + cost) / new_amt
            pos.amount = new_amt
            self.state.usdt -= total
        elif side == "sell":
            proceeds = price * amount - fee
            pnl = (price - pos.avg_cost) * amount - fee
            pos.amount -= amount
            if pos.amount <= 1e-12:
                pos.amount = 0.0
                pos.avg_cost = 0.0
            self.state.usdt += proceeds
            self.state.realized_pnl += pnl
        return pnl

    async def execute(
        self,
        session: AsyncSession,
        side: str,
        price: float,
        quote_amount: float,
        symbol: str | None = None,
        note: str = "",
    ) -> Trade | None:
        """Execute a buy/sell for a given USDT amount at ``price``.

        Returns ``None`` if there aren't enough funds / holdings to execute.
        """
        if side not in {"buy", "sell"}:
            raise ValueError(f"invalid side: {side}")
        if quote_amount <= 0 or price <= 0:
            return None

        sym = symbol or settings.symbol
        pos = self.position(sym)
        fee_rate = settings.paper_fee_bps / 10_000.0

        if side == "buy":
            fee = quote_amount * fee_rate
            spend = quote_amount + fee
            if spend > self.state.usdt + 1e-9:
                spend = max(0.0, self.state.usdt)
                quote_amount = spend / (1.0 + fee_rate)
                fee = quote_amount * fee_rate
                if quote_amount <= 0:
                    return None
            amount = quote_amount / price
        else:  # sell
            if pos.amount <= 1e-9:
                return None
            max_quote = pos.amount * price
            if quote_amount > max_quote:
                quote_amount = max_quote
            amount = quote_amount / price
            fee = quote_amount * fee_rate

        pnl = self._apply(sym, side, price, amount, fee)
        trade = Trade(
            mode="paper",
            symbol=sym,
            side=side,
            price=price,
            amount=amount,
            quote_amount=quote_amount,
            fee=fee,
            pnl=pnl,
            note=note,
        )
        session.add(trade)
        await session.flush()
        return trade

    def equity(self, mark_prices: dict[str, float] | float) -> float:
        """Total equity = USDT cash + sum(position_size * mark_price).

        For back-compat, accepts a single float (applied to the primary
        symbol only) or a dict mapping symbol -> mark price.
        """
        if isinstance(mark_prices, (int, float)):
            mp = {settings.symbol: float(mark_prices)}
        else:
            mp = mark_prices
        total = self.state.usdt
        for sym, pos in self.state.positions.items():
            if pos.amount <= 0:
                continue
            price = mp.get(sym, pos.avg_cost)
            total += pos.amount * price
        return total


paper_trader = PaperTrader()
