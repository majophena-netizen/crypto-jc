"""Binance exchange wrapper using ccxt.

Defaults to testnet for live trading. Market data (OHLCV/ticker) is fetched
without authentication from the public mainnet endpoint so the dashboard
works even without API keys.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import ccxt  # type: ignore[import-untyped]

from app.config import settings


@dataclass
class Candle:
    ts: int
    open: float
    high: float
    low: float
    close: float
    volume: float


_PUBLIC_FALLBACKS = ("binance", "kraken", "coinbase")


def _symbol_for(client: ccxt.Exchange, symbol: str) -> str:
    """Map our canonical BTC/USDT symbol to the one used by the given exchange."""
    # Kraken exposes BTC as XBT and BTC/USDT only on some books; BTC/USD is universal.
    if client.id == "kraken":
        return "BTC/USD" if symbol == "BTC/USDT" else symbol
    if client.id == "coinbase":
        return "BTC-USD" if symbol == "BTC/USDT" else symbol
    return symbol


def _public_client(preferred: str | None = None) -> ccxt.Exchange:
    name = (preferred or settings.market_data_exchange).lower()
    if not hasattr(ccxt, name):
        name = "binance"
    return getattr(ccxt, name)({"enableRateLimit": True})


def _private_client() -> ccxt.binance:
    client = ccxt.binance(
        {
            "apiKey": settings.binance_api_key,
            "secret": settings.binance_api_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
    )
    if settings.binance_testnet:
        client.set_sandbox_mode(True)
    return client


async def _with_fallback(fn):
    """Try the configured public exchange, then fall back to others on failure."""
    last_exc: Exception | None = None
    tried: set[str] = set()
    order = [settings.market_data_exchange.lower(), *_PUBLIC_FALLBACKS]
    for name in order:
        if name in tried:
            continue
        tried.add(name)
        try:
            client = _public_client(name)
            return await fn(client)
        except Exception as exc:  # pragma: no cover - depends on network
            last_exc = exc
            continue
    assert last_exc is not None
    raise last_exc


async def fetch_ohlcv(
    symbol: str | None = None, timeframe: str | None = None, limit: int = 200
) -> list[Candle]:
    sym_req = symbol or settings.symbol
    tf = timeframe or settings.timeframe

    async def run(client: ccxt.Exchange) -> list[Candle]:
        sym = _symbol_for(client, sym_req)
        raw = await asyncio.to_thread(client.fetch_ohlcv, sym, tf, None, limit)
        return [Candle(*row) for row in raw]

    return await _with_fallback(run)


async def fetch_ticker(symbol: str | None = None) -> dict:
    sym_req = symbol or settings.symbol

    async def run(client: ccxt.Exchange) -> dict:
        sym = _symbol_for(client, sym_req)
        t = await asyncio.to_thread(client.fetch_ticker, sym)
        # Normalize to a common symbol for downstream consumers.
        t = dict(t)
        t["symbol"] = sym_req
        t["source"] = client.id
        return t

    return await _with_fallback(run)


async def fetch_balance() -> dict:
    if not settings.binance_api_key or not settings.binance_api_secret:
        raise RuntimeError("Binance API credentials not configured")
    client = _private_client()
    return await asyncio.to_thread(client.fetch_balance)


async def create_market_order(side: str, amount: float, symbol: str | None = None) -> dict:
    """Place a market order on Binance (testnet unless disabled)."""
    if side not in {"buy", "sell"}:
        raise ValueError(f"invalid side: {side}")
    if not settings.binance_api_key or not settings.binance_api_secret:
        raise RuntimeError("Binance API credentials not configured")
    sym = symbol or settings.symbol
    client = _private_client()
    return await asyncio.to_thread(client.create_order, sym, "market", side, amount)


def is_testnet() -> bool:
    return settings.binance_testnet


def has_live_credentials() -> bool:
    return bool(settings.binance_api_key and settings.binance_api_secret)
