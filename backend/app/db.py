"""Async SQLAlchemy database setup and ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Float, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now(), index=True)
    symbol: Mapped[str] = mapped_column(String(20))
    timeframe: Mapped[str] = mapped_column(String(10))
    price: Mapped[float] = mapped_column(Float)
    action: Mapped[str] = mapped_column(String(8))  # buy | sell | hold
    score: Mapped[float] = mapped_column(Float, default=0.0)  # -1..1
    rsi: Mapped[float] = mapped_column(Float, default=0.0)
    macd: Mapped[float] = mapped_column(Float, default=0.0)
    macd_signal: Mapped[float] = mapped_column(Float, default=0.0)
    ma_fast: Mapped[float] = mapped_column(Float, default=0.0)
    ma_slow: Mapped[float] = mapped_column(Float, default=0.0)
    ai_action: Mapped[str] = mapped_column(String(8), default="hold")
    ai_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    ai_rationale: Mapped[str] = mapped_column(Text, default="")
    explanation: Mapped[str] = mapped_column(Text, default="")


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(default=_utcnow, server_default=func.now(), index=True)
    mode: Mapped[str] = mapped_column(String(10))  # paper | live
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[str] = mapped_column(String(4))  # buy | sell
    price: Mapped[float] = mapped_column(Float)
    amount: Mapped[float] = mapped_column(Float)  # base units (BTC)
    quote_amount: Mapped[float] = mapped_column(Float)  # USDT value
    fee: Mapped[float] = mapped_column(Float, default=0.0)
    pnl: Mapped[float] = mapped_column(Float, default=0.0)  # realized pnl on sells
    external_id: Mapped[str] = mapped_column(String(64), default="")
    note: Mapped[str] = mapped_column(Text, default="")


engine = create_async_engine(settings.database_url, echo=False, future=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with SessionLocal() as session:
        yield session
