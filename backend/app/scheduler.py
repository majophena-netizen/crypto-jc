"""Background scanner that periodically runs the signal pipeline."""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.db import SessionLocal
from app.signals import scan
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
                    execute_paper = runtime.mode == "paper"
                    result = await scan(session, execute_paper=execute_paper)
                    runtime.mark_scan(result.snapshot.price, result.final_action)
                    # Live execution hook: only if mode==live and action is buy/sell.
                    if runtime.mode == "live" and result.final_action in {"buy", "sell"}:
                        try:
                            from app.live import execute_live  # local to avoid cycles
                            await execute_live(
                                session,
                                side=result.final_action,
                                price=result.snapshot.price,
                                quote_amount=settings.live_max_order_usdt,
                                note=f"auto live trade; {result.explanation}",
                            )
                        except Exception as exc:
                            logger.exception("Live execution failed: %s", exc)
                            runtime.push_error(f"live: {exc}")
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
            logger.info("Scanner started (interval=%ss)", settings.scan_interval_seconds)

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task


scanner = Scanner()
