"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the trading backend.

    All secrets must come from the environment. Never hard-code credentials.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Exchange ---
    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    # Default to testnet to avoid accidents with real money.
    binance_testnet: bool = Field(default=True, alias="BINANCE_TESTNET")
    # Public market-data source. Binance is blocked in some regions (HTTP 451);
    # falling back to Kraken or Coinbase keeps the dashboard working while you
    # still execute real orders against Binance. Accepts any ccxt id.
    market_data_exchange: str = Field(default="binance", alias="MARKET_DATA_EXCHANGE")

    # --- AI ---
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-sonnet-4-5", alias="ANTHROPIC_MODEL"
    )

    # --- Trading symbol / timeframe ---
    symbol: str = Field(default="BTC/USDT", alias="TRADING_SYMBOL")
    timeframe: str = Field(default="15m", alias="TRADING_TIMEFRAME")

    # --- Default mode on startup: "signals" | "paper" | "live" ---
    default_mode: str = Field(default="paper", alias="DEFAULT_MODE")

    # --- Paper trading ---
    paper_starting_usdt: float = Field(default=10_000.0, alias="PAPER_STARTING_USDT")
    paper_fee_bps: float = Field(default=10.0, alias="PAPER_FEE_BPS")  # 0.10%

    # --- Live trading safety ---
    live_max_order_usdt: float = Field(default=50.0, alias="LIVE_MAX_ORDER_USDT")

    # --- Strategy knobs ---
    rsi_period: int = Field(default=14, alias="RSI_PERIOD")
    rsi_oversold: float = Field(default=30.0, alias="RSI_OVERSOLD")
    rsi_overbought: float = Field(default=70.0, alias="RSI_OVERBOUGHT")
    macd_fast: int = Field(default=12, alias="MACD_FAST")
    macd_slow: int = Field(default=26, alias="MACD_SLOW")
    macd_signal: int = Field(default=9, alias="MACD_SIGNAL")
    ma_fast: int = Field(default=20, alias="MA_FAST")
    ma_slow: int = Field(default=50, alias="MA_SLOW")

    # --- Scheduler ---
    scan_interval_seconds: int = Field(default=60, alias="SCAN_INTERVAL_SECONDS")
    use_ai_confirmation: bool = Field(default=True, alias="USE_AI_CONFIRMATION")

    # --- Storage ---
    database_url: str = Field(
        default="sqlite+aiosqlite:///./trader.db", alias="DATABASE_URL"
    )

    # --- CORS (frontend origin) ---
    cors_origins: str = Field(default="*", alias="CORS_ORIGINS")


settings = Settings()
