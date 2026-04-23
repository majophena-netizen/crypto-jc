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
    # Gemini (Google AI Studio). Free tier: 60 RPM without a card.
    # Accepts either GEMINI_API_KEY or GEMINI_API as the env name.
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "GEMINI_API"),
    )
    # gemini-2.5-flash is often overloaded on free tier; flash-lite is more
    # stable and still plenty good for a short JSON verdict.
    gemini_model: str = Field(
        default="gemini-2.5-flash-lite", alias="GEMINI_MODEL"
    )
    gemini_fallback_model: str = Field(
        default="gemini-flash-latest", alias="GEMINI_FALLBACK_MODEL"
    )
    # Which provider to use when both are configured.
    # Accepts: "auto" (prefer gemini if set, else anthropic), "gemini", "anthropic".
    ai_provider: str = Field(default="auto", alias="AI_PROVIDER")

    @property
    def active_ai_provider(self) -> str:
        """Returns the actual provider to use based on configuration."""
        choice = (self.ai_provider or "auto").lower()
        if choice == "gemini" and self.gemini_api_key:
            return "gemini"
        if choice == "anthropic" and self.anthropic_api_key:
            return "anthropic"
        # auto / fallback
        if self.gemini_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        return ""

    # --- Trading symbol / timeframe ---
    # Primary symbol used by single-symbol endpoints (market/ticker, etc.).
    symbol: str = Field(default="BTC/USDT", alias="TRADING_SYMBOL")
    timeframe: str = Field(default="15m", alias="TRADING_TIMEFRAME")
    # Comma-separated list of symbols the scanner scans every tick. The
    # autotrader picks the best BUY signal(s) across this universe.
    scan_symbols_csv: str = Field(
        default="BTC/USDT,ETH/USDT,SOL/USDT,BNB/USDT,XRP/USDT,DOGE/USDT,ADA/USDT,AVAX/USDT",
        alias="SCAN_SYMBOLS",
    )

    @property
    def scan_symbols(self) -> list[str]:
        raw = self.scan_symbols_csv or self.symbol
        out: list[str] = []
        for piece in raw.split(","):
            s = piece.strip().upper()
            if s and s not in out:
                out.append(s)
        return out or [self.symbol]

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

    # --- Auto-trading (bot opens/closes positions by itself) ---
    auto_trade_enabled: bool = Field(default=True, alias="AUTO_TRADE_ENABLED")
    # Size of each entry, in USDT. Paper defaults to 10% of starting capital.
    entry_position_usdt: float = Field(default=1000.0, alias="ENTRY_POSITION_USDT")
    # Exit the position if unrealized PnL reaches +take_profit_pct %.
    take_profit_pct: float = Field(default=2.0, alias="TAKE_PROFIT_PCT")
    # Exit the position if unrealized PnL drops below -stop_loss_pct %.
    stop_loss_pct: float = Field(default=1.5, alias="STOP_LOSS_PCT")
    # Minimum AI confidence required to open a position on a BUY signal.
    min_ai_confidence: float = Field(default=0.4, alias="MIN_AI_CONFIDENCE")
    # Cooldown between auto trades, in seconds, to avoid churn.
    auto_trade_cooldown_seconds: int = Field(default=120, alias="AUTO_TRADE_COOLDOWN_SECONDS")
    # Max simultaneous open positions across all scanned symbols.
    max_concurrent_positions: int = Field(default=3, alias="MAX_CONCURRENT_POSITIONS")

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
