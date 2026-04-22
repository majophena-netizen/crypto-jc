"""Global mutable runtime state (trading mode + last scan)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.config import settings


@dataclass
class RuntimeState:
    mode: str = settings.default_mode  # signals | paper | live
    last_scan_at: datetime | None = None
    last_action: str = "hold"
    last_price: float = 0.0
    errors: list[str] = field(default_factory=list)

    def set_mode(self, mode: str) -> None:
        if mode not in {"signals", "paper", "live"}:
            raise ValueError(f"invalid mode: {mode}")
        self.mode = mode

    def mark_scan(self, price: float, action: str) -> None:
        self.last_scan_at = datetime.now(UTC)
        self.last_price = price
        self.last_action = action

    def push_error(self, msg: str) -> None:
        self.errors.append(msg)
        # Keep last 20.
        self.errors = self.errors[-20:]


runtime = RuntimeState()
