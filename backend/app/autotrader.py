"""Autonomous multi-pair trading manager.

Given a ranked list of signal results (one per scanned symbol), this module:

1. Always evaluates exit conditions on every open position (TP, SL, SELL signal).
2. Then opens new positions on the best BUY signals across the universe,
   respecting ``max_concurrent_positions`` and available capital.

Shared knobs (configurable at runtime via /api/control/autotrader):
- ``auto_trade_enabled``: master switch
- ``entry_position_usdt``: USDT per entry
- ``take_profit_pct`` / ``stop_loss_pct``: exit thresholds
- ``min_ai_confidence``: required AI confidence to enter
- ``auto_trade_cooldown_seconds``: global cooldown between trades
- ``max_concurrent_positions``: simultaneous open positions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app import exchange
from app.config import settings
from app.db import Trade
from app.live import execute_live
from app.paper import paper_trader
from app.signals import SignalResult
from app.state import runtime

logger = logging.getLogger(__name__)


@dataclass
class AutoTradeDecision:
    symbol: str
    action: str  # "entry" | "exit_tp" | "exit_sl" | "exit_signal" | "hold" | "skip"
    reason: str
    trade: Trade | None = None


@dataclass
class AutoTraderState:
    last_trade_at: datetime | None = None
    last_decisions: list[str] = field(default_factory=list)

    def record(self, symbol: str, action: str, reason: str) -> None:
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        entry = f"{ts} [{symbol}] {action}: {reason}"
        self.last_decisions.append(entry)
        if len(self.last_decisions) > 30:
            self.last_decisions = self.last_decisions[-30:]


state = AutoTraderState()


def _in_cooldown() -> bool:
    if state.last_trade_at is None:
        return False
    delta = (datetime.now(UTC) - state.last_trade_at).total_seconds()
    return delta < settings.auto_trade_cooldown_seconds


def _pnl_pct(avg_cost: float, price: float) -> float:
    if avg_cost <= 0:
        return 0.0
    return ((price - avg_cost) / avg_cost) * 100.0


async def _paper_position(symbol: str) -> tuple[float, float]:
    pos = paper_trader.state.positions.get(symbol)
    if pos is None:
        return 0.0, 0.0
    return pos.amount, pos.avg_cost


def _base_asset(symbol: str) -> str:
    return symbol.split("/")[0] if "/" in symbol else symbol


async def _live_position(symbol: str) -> tuple[float, float]:
    """Returns (qty, avg_cost_estimate) for the base asset of ``symbol``.

    Binance does not return avg-cost; we track it in ``runtime.live_avg_cost``
    (dict per symbol), set on entry and cleared on exit.
    """
    try:
        bal = await exchange.fetch_balance()
        total = bal.get("total", {}) or {}
        qty = float(total.get(_base_asset(symbol), 0.0) or 0.0)
    except Exception as exc:
        logger.warning("live balance fetch failed: %s", exc)
        return 0.0, 0.0
    return qty, runtime.live_avg_cost.get(symbol, 0.0)


async def _position(mode: str, symbol: str) -> tuple[float, float]:
    if mode == "paper":
        return await _paper_position(symbol)
    return await _live_position(symbol)


def _count_open_positions(mode: str) -> int:
    if mode == "paper":
        return len(paper_trader.open_positions())
    # Live: we approximate via the runtime.live_avg_cost dict (entries with >0
    # avg_cost). This is best-effort; fetch_balance would be authoritative but
    # costly and called per-symbol elsewhere.
    return sum(1 for v in runtime.live_avg_cost.values() if v > 0)


async def _open(
    session: AsyncSession, mode: str, symbol: str, price: float, reason: str
) -> AutoTradeDecision:
    if mode == "paper":
        quote = min(settings.entry_position_usdt, paper_trader.state.usdt)
        if quote <= 0:
            return AutoTradeDecision(symbol, "skip", "insufficient paper USDT")
        trade = await paper_trader.execute(
            session, side="buy", price=price, quote_amount=quote,
            symbol=symbol, note=f"auto entry: {reason}",
        )
        await session.commit()
    else:
        quote = min(settings.entry_position_usdt, settings.live_max_order_usdt)
        if quote <= 0:
            return AutoTradeDecision(symbol, "skip", "live cap <= 0")
        trade = await execute_live(
            session, side="buy", price=price, quote_amount=quote,
            symbol=symbol, note=f"auto entry: {reason}",
        )
        if trade is not None:
            runtime.live_avg_cost[symbol] = trade.price

    if trade is None:
        return AutoTradeDecision(symbol, "skip", "broker rejected entry")

    state.last_trade_at = datetime.now(UTC)
    state.record(symbol, "entry", reason)
    logger.info("AUTO ENTRY (%s %s): %.6f @ %.4f", mode, symbol, trade.amount, trade.price)
    return AutoTradeDecision(symbol, "entry", reason, trade)


async def _close(
    session: AsyncSession,
    mode: str,
    symbol: str,
    qty: float,
    price: float,
    reason: str,
    tag: str,
) -> AutoTradeDecision:
    quote = qty * price
    if mode == "paper":
        trade = await paper_trader.execute(
            session, side="sell", price=price, quote_amount=quote,
            symbol=symbol, note=f"auto {tag}: {reason}",
        )
        await session.commit()
    else:
        trade = await execute_live(
            session, side="sell", price=price, quote_amount=quote,
            symbol=symbol, note=f"auto {tag}: {reason}",
        )
        runtime.live_avg_cost.pop(symbol, None)

    if trade is None:
        return AutoTradeDecision(symbol, "skip", "broker rejected exit")

    state.last_trade_at = datetime.now(UTC)
    state.record(symbol, tag, reason)
    logger.info("AUTO %s (%s %s): %.6f @ %.4f", tag.upper(), mode, symbol, trade.amount, trade.price)
    return AutoTradeDecision(symbol, tag, reason, trade)


async def tick_symbol(
    session: AsyncSession, result: SignalResult, mode: str, allow_entry: bool
) -> AutoTradeDecision:
    """Evaluate one symbol: always check exits; optionally open an entry."""
    symbol = result.symbol
    price = result.snapshot.price
    if price <= 0:
        return AutoTradeDecision(symbol, "skip", "no price")

    qty, avg_cost = await _position(mode, symbol)
    has_position = qty > 1e-8

    # --- Exits first ---
    if has_position and avg_cost > 0:
        pnl_pct = _pnl_pct(avg_cost, price)
        if pnl_pct >= settings.take_profit_pct:
            return await _close(
                session, mode, symbol, qty, price,
                reason=f"take-profit ({pnl_pct:+.2f}% >= {settings.take_profit_pct:.2f}%)",
                tag="exit_tp",
            )
        if pnl_pct <= -settings.stop_loss_pct:
            return await _close(
                session, mode, symbol, qty, price,
                reason=f"stop-loss ({pnl_pct:+.2f}% <= -{settings.stop_loss_pct:.2f}%)",
                tag="exit_sl",
            )
        if result.final_action == "sell":
            if _in_cooldown():
                return AutoTradeDecision(symbol, "hold", "sell signal but in cooldown")
            return await _close(
                session, mode, symbol, qty, price,
                reason=f"SELL signal ({pnl_pct:+.2f}%); {result.explanation}",
                tag="exit_signal",
            )
        return AutoTradeDecision(symbol, "hold", f"holding ({pnl_pct:+.2f}%)")

    # --- Entry ---
    if not allow_entry:
        return AutoTradeDecision(symbol, "skip", "entry slot unavailable")
    if result.final_action != "buy":
        return AutoTradeDecision(symbol, "hold", f"no buy signal (final={result.final_action})")
    if _in_cooldown():
        return AutoTradeDecision(symbol, "hold", "buy signal but in cooldown")
    if result.verdict.confidence < settings.min_ai_confidence:
        msg = (
            f"AI confidence {result.verdict.confidence:.2f} < "
            f"{settings.min_ai_confidence:.2f}"
        )
        state.record(symbol, "skip", msg)
        return AutoTradeDecision(symbol, "skip", msg)

    return await _open(
        session, mode, symbol, price,
        reason=f"BUY signal conv={result.conviction:+.2f}, AI conf {result.verdict.confidence:.2f}",
    )


async def tick(
    session: AsyncSession, results: list[SignalResult], mode: str
) -> list[AutoTradeDecision]:
    """Process all scanned symbols in one pass.

    Phase 1: exit-check every symbol (including those without a current
    signal — but we only have signals for scanned symbols; that's fine since
    we rebuild paper state from DB at start of tick).

    Phase 2: among symbols flat and with BUY signals (ranked by conviction),
    open new entries until we hit ``max_concurrent_positions``.
    """
    decisions: list[AutoTradeDecision] = []
    if mode not in {"paper", "live"}:
        return decisions
    if not settings.auto_trade_enabled:
        return decisions

    # Rehydrate paper state once so position() reads match the DB.
    if mode == "paper":
        await paper_trader.rehydrate(session)

    # --- Phase 1: exits (no entries yet) ---
    phase1: list[AutoTradeDecision] = []
    for r in results:
        d = await tick_symbol(session, r, mode, allow_entry=False)
        phase1.append(d)
    decisions.extend(phase1)

    # --- Phase 2: entries on remaining slots ---
    open_count = _count_open_positions(mode)
    max_slots = max(0, settings.max_concurrent_positions - open_count)

    if max_slots > 0:
        # Only results that generated a BUY signal are entry candidates.
        buy_candidates = [
            r for r in results if r.final_action == "buy" and r.conviction > 0
        ]
        # Already sorted by conviction desc, but re-sort to be safe.
        buy_candidates.sort(key=lambda r: r.conviction, reverse=True)

        for r in buy_candidates:
            # Skip if we already have a position on this symbol (from phase 1
            # or pre-existing).
            qty, _ = await _position(mode, r.symbol)
            if qty > 1e-8:
                continue
            if max_slots <= 0:
                break
            d = await tick_symbol(session, r, mode, allow_entry=True)
            decisions.append(d)
            if d.action == "entry":
                max_slots -= 1

    return decisions
