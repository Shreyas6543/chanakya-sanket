from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    env: str = "development"
    log_level: str = "INFO"

    # Upstox
    upstox_api_key: str
    upstox_api_secret: str
    upstox_redirect_uri: str = "http://127.0.0.1:8000/auth/callback"
    upstox_access_token: str = ""

    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str

    # PostgreSQL
    postgres_user: str = "trading"
    postgres_password: str = "trading_secret"
    postgres_db: str = "trading_engine"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379

    # Trading rules
    capital_base: float = 500_000
    max_capital_per_trade_pct: float = 10.0   # Max 10% of capital per trade
    risk_per_trade_pct: float = 1.5           # Risk (SL distance) as % of capital
    max_daily_loss_pct: float = 5.0
    max_open_signals_per_symbol: int = 2
    min_confidence_score: int = 35

    # ATR regime threshold (fraction of 20-period average)
    atr_sideways_threshold: float = 0.70

    # Trend Efficiency filter — skip signal if market efficiency ratio < this value.
    # Efficiency = net directional move / total range. < 0.5 = choppy/whipsaw day.
    # Backtested threshold: 0.50 separates all 4 wipeout days from winning days.
    min_trend_efficiency: float = 0.50

    # Lot sizes (NSE standard — update if NSE changes them)
    nifty_lot_size: int = 25
    banknifty_lot_size: int = 15

    # Strike intervals (NSE standard)
    nifty_strike_interval: int = 50
    banknifty_strike_interval: int = 100

    # Expiry selection — switch to next expiry if days remaining <= this
    expiry_min_days: int = 2

    # Option premium estimation (used until live options chain available)
    premium_atr_multiplier: float = 1.2   # estimated_premium = ATR * this
    premium_sl_loss_ratio: float = 0.5    # assume 50% of premium lost at SL

    # Strategy confidence points (scoring formula)
    points_vwap_breakout: int = 20
    points_oi_buildup: int = 25
    points_rsi_momentum: int = 15
    points_bullish_engulfing: int = 15
    points_opening_range: int = 15
    points_positive_sentiment: int = 10

    # Strategy thresholds
    rsi_crossover_level: float = 55.0
    volume_spike_multiplier: float = 1.5
    oi_buildup_threshold: float = 0.01    # 1% OI change — calibrated for real day-over-day NSE data
    vwap_tolerance_pct: float = 0.002     # Within 0.2% of VWAP = "near VWAP"

    # Instruments to track
    instruments: str = "NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"

    @property
    def instrument_list(self) -> list[str]:
        return [i.strip() for i in self.instruments.split(",")]

    @property
    def max_capital_per_trade(self) -> float:
        """Maximum money to deploy in a single trade — 10% of capital by default."""
        return self.capital_base * (self.max_capital_per_trade_pct / 100)

    @property
    def risk_amount(self) -> float:
        """Max loss acceptable per trade — 1.5% of capital by default."""
        return self.capital_base * (self.risk_per_trade_pct / 100)

    @property
    def max_daily_loss_amount(self) -> float:
        return self.capital_base * (self.max_daily_loss_pct / 100)


@lru_cache
def get_settings() -> Settings:
    return Settings()
