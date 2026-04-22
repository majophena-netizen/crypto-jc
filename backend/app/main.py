"""FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import SessionLocal, init_db
from app.paper import paper_trader
from app.routers import control, market, signals, trades
from app.scheduler import scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with SessionLocal() as session:
        await paper_trader.rehydrate(session)
    scanner.start()
    try:
        yield
    finally:
        await scanner.stop()


app = FastAPI(
    title="Crypto Trader API",
    description="BTC/USDT signals, paper trading and live trading with Claude AI confirmation.",
    version="0.1.0",
    lifespan=lifespan,
)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router)
app.include_router(signals.router)
app.include_router(trades.router)
app.include_router(control.router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
