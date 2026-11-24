from sqlalchemy import (
    Column, String, Float, Integer, BigInteger, SmallInteger,
    Boolean, Text, DateTime, ARRAY, JSON, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class Instrument(Base):
    """Stock/ETF metadata."""
    __tablename__ = "instruments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)  # NSE, BSE, NASDAQ, NYSE
    name = Column(String(200))
    sector = Column(String(100))
    market_cap_category = Column(String(20))  # large, mid, small
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("symbol", "exchange", name="uq_instrument"),
    )


class Candle(Base):
    """OHLCV candle data — partitioned by ts in TimescaleDB."""
    __tablename__ = "candles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), nullable=False)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    interval = Column(String(5), nullable=False)  # 1m, 5m, 15m, 1d
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("ts", "symbol", "exchange", "interval", name="uq_candle"),
        Index("ix_candle_symbol_ts", "symbol", "ts"),
    )


class Feature(Base):
    """Pre-computed technical features per symbol per day."""
    __tablename__ = "features"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), nullable=False)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)

    # Momentum
    rsi_14 = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_hist = Column(Float)

    # Volatility
    bb_upper = Column(Float)
    bb_lower = Column(Float)
    bb_pct = Column(Float)   # (close - lower) / (upper - lower)
    atr_14 = Column(Float)

    # Trend
    ema_20 = Column(Float)
    ema_50 = Column(Float)
    ema_200 = Column(Float)
    price_vs_ema20 = Column(Float)   # % above/below EMA20
    adx = Column(Float)

    # Volume
    obv = Column(Float)
    obv_change_5d = Column(Float)
    volume_ratio_20d = Column(Float)   # today / 20d avg

    # Relative strength
    sector_rel_perf_5d = Column(Float)

    __table_args__ = (
        UniqueConstraint("ts", "symbol", "exchange", name="uq_feature"),
        Index("ix_feature_symbol_ts", "symbol", "ts"),
    )


class Fundamental(Base):
    """Company fundamentals — updated weekly."""
    __tablename__ = "fundamentals"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    pe_ratio = Column(Float)
    pb_ratio = Column(Float)
    eps = Column(Float)
    eps_growth_yoy = Column(Float)
    revenue_growth_yoy = Column(Float)
    debt_to_equity = Column(Float)
    roe = Column(Float)
    market_cap = Column(BigInteger)
    dividend_yield = Column(Float)

    # Sector comparison (populated by feature job)
    pe_vs_sector = Column(Float)   # z-score vs sector median


class NewsItem(Base):
    """News headlines with FinBERT sentiment scores."""
    __tablename__ = "news_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    headline = Column(Text, nullable=False)
    url = Column(Text)
    source = Column(String(100))
    published_at = Column(DateTime(timezone=True), nullable=False)
    symbols_mentioned = Column(ARRAY(String))
    finbert_label = Column(String(10))   # positive, negative, neutral
    finbert_score = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Signal(Base):
    """Generated trading signals with sub-scores and reasons."""
    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

    # Direction: 1=buy, -1=sell, 0=hold
    direction = Column(SmallInteger, nullable=False)
    confidence = Column(Float, nullable=False)   # 0.0 → 1.0

    # Sub-scores
    ta_score = Column(Float)
    sentiment_score = Column(Float)
    fundamental_score = Column(Float)

    # Human-readable reasoning
    signal_reasons = Column(JSONB)   # list of strings

    # Backtest reference
    price_at_signal = Column(Float)
    actual_return_5d = Column(Float)   # filled by nightly backtest job
    backtest_correct = Column(Boolean)

    __table_args__ = (
        Index("ix_signal_symbol_ts", "symbol", "generated_at"),
    )


class User(Base):
    """App users."""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    tier = Column(String(20), default="free")   # free, pro, team
    telegram_chat_id = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    watchlist = relationship("WatchlistItem", back_populates="user")
    alerts = relationship("AlertRule", back_populates="user")


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="watchlist")


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    symbol = Column(String(20), nullable=False)
    exchange = Column(String(10), nullable=False)
    direction = Column(SmallInteger)   # None=any, 1=buy only, -1=sell only
    min_confidence = Column(Float, default=0.6)
    channel = Column(String(20), default="telegram")  # telegram, email, both
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="alerts")


class PipelineRun(Base):
    """Tracks ingestion job runs for monitoring."""
    __tablename__ = "pipeline_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_name = Column(String(100), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    status = Column(String(20))   # running, success, failed
    records_processed = Column(Integer, default=0)
    error_message = Column(Text)
