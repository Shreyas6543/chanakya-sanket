from datetime import datetime
from sqlalchemy import (
    String, Float, Integer, Boolean, DateTime, JSON,
    ForeignKey, Enum as SAEnum, Text, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum

from app.db.database import Base


class SignalDirection(str, enum.Enum):
    CALL = "CALL"
    PUT = "PUT"


class SignalState(str, enum.Enum):
    OPEN = "OPEN"
    TARGET_HIT = "TARGET_HIT"
    SL_HIT = "SL_HIT"
    EXPIRED = "EXPIRED"
    USER_CLOSED = "USER_CLOSED"  # User manually squared off via Telegram button


class MarketRegime(str, enum.Enum):
    TRENDING = "TRENDING"
    SIDEWAYS = "SIDEWAYS"


class SentimentLabel(str, enum.Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class Candle(Base):
    __tablename__ = "candles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), default="5m")
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_candles_symbol_timestamp", "symbol", "timestamp"),
    )


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    direction: Mapped[SignalDirection] = mapped_column(SAEnum(SignalDirection), nullable=False)

    # Strike & expiry
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    expiry: Mapped[str] = mapped_column(String(20), nullable=False)

    # Levels
    entry: Mapped[float] = mapped_column(Float, nullable=False)
    stop_loss: Mapped[float] = mapped_column(Float, nullable=False)
    target: Mapped[float] = mapped_column(Float, nullable=False)

    # Confidence & reasoning
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)
    reasons: Mapped[dict] = mapped_column(JSON, nullable=False)  # {reason: points}

    # Context
    regime: Mapped[MarketRegime] = mapped_column(SAEnum(MarketRegime), nullable=False)
    capital_required: Mapped[float] = mapped_column(Float, nullable=False)
    suggested_lots: Mapped[int] = mapped_column(Integer, default=1)

    # Source — "live" for real Upstox data, "mock" for test/forced signals
    source: Mapped[str] = mapped_column(String(10), default="live", nullable=False)

    # Signal context snapshot — market conditions at the exact moment the signal fired
    # Keys: signal_time, hour, minute, rsi, vwap_distance_pct, atr, pcr, ce_oi, pe_oi, strategies_fired
    signal_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Lifecycle
    state: Mapped[SignalState] = mapped_column(SAEnum(SignalState), default=SignalState.OPEN)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    outcome: Mapped["SignalOutcome"] = relationship("SignalOutcome", back_populates="signal", uselist=False)
    strategy_results: Mapped[list["StrategyResult"]] = relationship("StrategyResult", back_populates="signal")

    __table_args__ = (
        Index("ix_signals_symbol_state", "symbol", "state"),
        Index("ix_signals_created_at", "created_at"),
    )


class SignalOutcome(Base):
    __tablename__ = "signal_outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), unique=True, nullable=False)

    mfe: Mapped[float | None] = mapped_column(Float, nullable=True)   # Max Favorable Excursion
    mae: Mapped[float | None] = mapped_column(Float, nullable=True)   # Max Adverse Excursion
    result: Mapped[str | None] = mapped_column(String(20), nullable=True)  # WIN / LOSS / EXPIRED
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    signal: Mapped["Signal"] = relationship("Signal", back_populates="outcome")


class StrategyResult(Base):
    __tablename__ = "strategy_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id"), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(100), nullable=False)
    contributed_points: Mapped[int] = mapped_column(Integer, nullable=False)
    fired: Mapped[bool] = mapped_column(Boolean, default=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    signal: Mapped["Signal"] = relationship("Signal", back_populates="strategy_results")


class NewsEvent(Base):
    __tablename__ = "news_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    sentiment: Mapped[SentimentLabel] = mapped_column(SAEnum(SentimentLabel), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        Index("ix_news_fetched_at", "fetched_at"),
    )


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    call_oi: Mapped[float | None] = mapped_column(Float, nullable=True)
    put_oi: Mapped[float | None] = mapped_column(Float, nullable=True)
    iv_percentile: Mapped[float | None] = mapped_column(Float, nullable=True)
    regime: Mapped[MarketRegime] = mapped_column(SAEnum(MarketRegime), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_snapshots_symbol_timestamp", "symbol", "timestamp"),
    )
