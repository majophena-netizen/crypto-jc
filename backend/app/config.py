"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pydantic import AliasChoices, Field
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
    # Mainnet keys. Only used when `binance_testnet` is false.
    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    # Testnet keys. When `binance_testnet` is true these are preferred over
    # the mainnet keys, so you can keep both sets in the same .env file.
    binance_testnet_key: str = Field(
        default="",
        validation_alias=AliasChoices("BINANCE_TESTNET_KEY", "BINANCE_DEMO_KEY"),
    )
    binance_testnet_secret: str = Field(
        default="",
        validation_alias=AliasChoices("BINANCE_TESTNET_SECRET", "BINANCE_DEMO_SECRET"),
    )
    # Default to testnet to avoid accidents with real money.
    # Accepts either BINANCE_TESTNET or BINANCE_API_TESTNET.
    binance_testnet: bool = Field(
        default=True,
        validation_alias=AliasChoices("BINANCE_TESTNET", "BINANCE_API_TESTNET"),
    )

    @property
    def active_binance_key(self) -> str:
        """Returns the API key matching the current testnet/mainnet mode."""
        if self.binance_testnet:
            return self.binance_testnet_key or self.binance_api_key
        return self.binance_api_key

    @property
    def active_binance_secret(self) -> str:
        if self.binance_testnet:
            return self.binance_testnet_secret or self.binance_api_secret
        return self.binance_api_secret
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
    paper_starting_usdt: float = Field(
        default=10_000.0,
        validation_alias=AliasChoices("PAPER_STARTING_USDT", "START_BALANCE"),
    )
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
