"""In-memory paper trading engine backed by persistent trades in the DB.

The engine maintains a virtual wallet (USDT + BTC) and records every simulated
trade in the ``trades`` table with ``mode='paper'``. Realized PnL is computed
using average-cost accounting on the BTC position.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import Trade

logger = logging.getLogger(__name__)


@dataclass
class PaperState:
    usdt: float
    btc: float
    avg_cost: float  # average cost basis of held BTC in USDT
    realized_pnl: float


class PaperTrader:
    """Singleton-ish paper trading bookkeeper.

    State is rebuilt from the DB on startup so restarts don't lose the
    virtual portfolio.
    """

    def __init__(self) -> None:
        self.state = PaperState(
            usdt=settings.paper_starting_usdt,
            btc=0.0,
            avg_cost=0.0,
            realized_pnl=0.0,
        )

    async def rehydrate(self, session: AsyncSession) -> None:
        self.state = PaperState(
            usdt=settings.paper_starting_usdt,
            btc=0.0,
            avg_cost=0.0,
            realized_pnl=0.0,
        )
        result = await session.execute(
            select(Trade).where(Trade.mode == "paper").order_by(Trade.ts.asc())
        )
        for tr in result.scalars().all():
            self._apply(tr.side, tr.price, tr.amount, tr.fee)

    def reset(self) -> PaperState:
        self.state = PaperState(
            usdt=settings.paper_starting_usdt,
            btc=0.0,
            avg_cost=0.0,
            realized_pnl=0.0,
        )
        return self.state

    def _apply(self, side: str, price: float, amount: float, fee: float) -> float:
        """Apply a fill to state, returning realized PnL for sells."""
        pnl = 0.0
        if side == "buy":
            cost = price * amount
            total = cost + fee
            new_btc = self.state.btc + amount
            # Update weighted average cost.
            if new_btc > 0:
                self.state.avg_cost = (
                    self.state.avg_cost * self.state.btc + cost
                ) / new_btc
            self.state.btc = new_btc
            self.state.usdt -= total
        elif side == "sell":
            proceeds = price * amount - fee
            pnl = (price - self.state.avg_cost) * amount - fee
            self.state.btc -= amount
            if self.state.btc <= 1e-12:
                self.state.btc = 0.0
                self.state.avg_cost = 0.0
            self.state.usdt += proceeds
            self.state.realized_pnl += pnl
        return pnl

    async def execute(
        self,
        session: AsyncSession,
        side: str,
        price: float,
        quote_amount: float,
        note: str = "",
    ) -> Trade | None:
        """Execute a buy/sell for a given USDT amount at ``price``.

        Returns ``None`` if there aren't enough funds / holdings to execute.
        """
        if side not in {"buy", "sell"}:
            raise ValueError(f"invalid side: {side}")
        if quote_amount <= 0 or price <= 0:
            return None

        fee_rate = settings.paper_fee_bps / 10_000.0

        if side == "buy":
            fee = quote_amount * fee_rate
            spend = quote_amount + fee
            if spend > self.state.usdt + 1e-9:
                # Scale down to available funds.
                spend = max(0.0, self.state.usdt)
                quote_amount = spend / (1.0 + fee_rate)
                fee = quote_amount * fee_rate
                if quote_amount <= 0:
                    return None
            amount = quote_amount / price
        else:  # sell
            if self.state.btc <= 1e-9:
                return None
            max_quote = self.state.btc * price
            if quote_amount > max_quote:
                quote_amount = max_quote
            amount = quote_amount / price
            fee = quote_amount * fee_rate

        pnl = self._apply(side, price, amount, fee)
        trade = Trade(
            mode="paper",
            symbol=settings.symbol,
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

    def equity(self, mark_price: float) -> float:
        return self.state.usdt + self.state.btc * mark_price


paper_trader = PaperTrader()
