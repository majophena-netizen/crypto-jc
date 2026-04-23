"""Background scanner that periodically runs the multi-pair signal pipeline."""

from __future__ import annotations

import asyncio
import logging

from app import autotrader
from app.config import settings
from app.db import SessionLocal
from app.signals import scan_all
from app.state import runtime

logger = logging.getLogger(__name__)


class Scanner:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                async with SessionLocal() as session:
                    results = await scan_all(session, settings.scan_symbols)

                    # Update runtime state with the best / primary result.
                    if results:
                        runtime.last_prices = {
                            r.symbol: r.snapshot.price for r in results
                        }
                        primary = next(
                            (r for r in results if r.symbol == settings.symbol),
                            results[0],
                        )
                        runtime.mark_scan(primary.snapshot.price, primary.final_action)

                    # Delegate entry/exit to the autotrader (paper + live).
                    if runtime.mode in {"paper", "live"} and results:
                        try:
                            decisions = await autotrader.tick(
                                session, results, mode=runtime.mode
                            )
                            for d in decisions:
                                if d.action not in {"hold", "skip"}:
                                    logger.info(
                                        "Autotrade [%s] %s: %s",
                                        d.symbol, d.action, d.reason,
                                    )
                        except Exception as exc:
                            logger.exception("Autotrader failed: %s", exc)
                            runtime.push_error(f"autotrader: {exc}")
            except Exception as exc:
                logger.exception("Scan loop error: %s", exc)
                runtime.push_error(str(exc))
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.scan_interval_seconds)
            except TimeoutError:
                pass

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.create_task(self._loop())
            logger.info(
                "Scanner started (interval=%ss, symbols=%s)",
                settings.scan_interval_seconds, ",".join(settings.scan_symbols),
            )

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task


scanner = Scanner()
