"""
APScheduler jobs — data ingestion + signal generation.
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, update, text

from app.db.database import AsyncSessionLocal
from app.db.models import Candle, Signal
from app.services.data_fetcher import (
    fetch_all_ohlcv, fetch_ohlcv, NSE_WATCHLIST, US_WATCHLIST
)
from app.services.news_fetcher import fetch_all_news
from app.ml.sentiment import score_headlines
from app.ml.signal_engine import generate_signal
from app.services.alert_service import dispatch_alerts
from app.services.kite_auth import login_and_get_token
from app.services.kite_ticker import get_ticker

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


async def job_fetch_eod_ohlcv():
    """Fetch end-of-day OHLCV for all watchlist stocks and upsert into DB."""
    logger.info("Starting EOD OHLCV fetch...")
    df = fetch_all_ohlcv(period="1y")
    if df.empty:
        logger.warning("No OHLCV data fetched")
        return

    # Bulk upsert into candles table (500 rows per batch)
    rows = df.to_dict(orient="records")
    batch_size = 500
    inserted = 0
    async with AsyncSessionLocal() as session:
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            await session.execute(
                text(
                    """
                    INSERT INTO candles (ts, symbol, exchange, interval, open, high, low, close, volume)
                    VALUES (:ts, :symbol, :exchange, :interval, :open, :high, :low, :close, :volume)
                    ON CONFLICT (ts, symbol, exchange, interval) DO UPDATE SET
                        open = EXCLUDED.open, high = EXCLUDED.high,
                        low = EXCLUDED.low, close = EXCLUDED.close,
                        volume = EXCLUDED.volume
                    """
                ),
                batch,
            )
            await session.commit()
            inserted += len(batch)

    logger.info(f"EOD OHLCV: upserted {inserted} candles from {len(df)} rows fetched")


async def job_fetch_and_score_news():
    """Fetch news + run FinBERT scoring."""
    logger.info("Starting news fetch + sentiment scoring...")
    all_symbols = NSE_WATCHLIST + US_WATCHLIST
    articles = fetch_all_news(all_symbols)
    scored = score_headlines(articles)

    # Upsert scored news into DB (url as dedup key)
    async with AsyncSessionLocal() as session:
        for item in scored:
            await session.execute(
                text(
                    """
                    INSERT INTO news_items
                        (headline, url, source, published_at, symbols_mentioned,
                         finbert_label, finbert_score)
                    VALUES
                        (:headline, :url, :source, :published_at, :symbols_mentioned,
                         :finbert_label, :finbert_score)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "headline": item.get("headline", ""),
                    "url": item.get("url", ""),
                    "source": item.get("source", ""),
                    "published_at": item.get("published_at") or datetime.now(timezone.utc),
                    "symbols_mentioned": item.get("symbols_mentioned", []),
                    "finbert_label": item.get("finbert_label"),
                    "finbert_score": item.get("finbert_score"),
                },
            )
        await session.commit()

    logger.info(f"Scored and saved {len(scored)} news items")
    return scored


async def job_generate_signals():
    """
    Main signal generation job.
    Runs after EOD data + news are both fresh.
    """
    logger.info("Starting signal generation...")
    all_symbols = [(s, "NSE") for s in NSE_WATCHLIST] + \
                  [(s, "NASDAQ") for s in US_WATCHLIST]

    from app.services.data_fetcher import fetch_ohlcv
    articles = await job_fetch_and_score_news()

    signals = []
    for symbol, exchange in all_symbols:
        df = fetch_ohlcv(symbol, exchange, period="6mo", interval="1d")
        signal = generate_signal(symbol, exchange, df, articles or [])
        if signal and signal.direction != 0 and signal.confidence >= 0.4:
            signals.append(signal)
            logger.info(
                f"Signal: {symbol} {'BUY' if signal.direction == 1 else 'SELL'} "
                f"conf={signal.confidence:.2f} vol={signal.volume_ratio}x"
            )

    # Persist signals to DB
    if signals:
        async with AsyncSessionLocal() as session:
            for sig in signals:
                db_signal = Signal(
                    symbol=sig.symbol,
                    exchange=sig.exchange,
                    direction=sig.direction,
                    confidence=sig.confidence,
                    ta_score=sig.momentum_score,
                    sentiment_score=sig.news_score,
                    fundamental_score=None,
                    signal_reasons=sig.reasons,
                    price_at_signal=sig.price,
                )
                session.add(db_signal)
            await session.commit()
        logger.info(f"Saved {len(signals)} signals to DB")

    logger.info(f"Generated {len(signals)} actionable signals")

    # Dispatch alerts for high-confidence signals
    high_conf = [s for s in signals if s.confidence >= 0.6]
    if high_conf:
        await dispatch_alerts(high_conf)

    return signals


async def job_kite_daily_login():
    """
    Refresh Kite access token daily at 08:00 IST before market open.
    Then restart ticker with fresh token.
    """
    logger.info("Running Kite daily login...")
    token = login_and_get_token()
    if token:
        logger.info("Kite token refreshed ✅")
        ticker = get_ticker()
        ticker.stop()
        import asyncio; await asyncio.sleep(2)
        ticker.start()
        logger.info("Kite ticker restarted with new token ✅")
    else:
        logger.error("Kite daily login failed ❌ — signals will use yfinance fallback")


async def job_backtest_evaluate():
    """
    Evaluate signals generated ~5 trading days ago.
    Fetches current price, computes actual_return_5d, marks backtest_correct.
    """
    logger.info("Running backtest evaluation...")
    since = datetime.now(timezone.utc) - timedelta(days=8)
    until = datetime.now(timezone.utc) - timedelta(days=5)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Signal)
            .where(Signal.generated_at >= since)
            .where(Signal.generated_at <= until)
            .where(Signal.actual_return_5d == None)  # noqa: E711
            .where(Signal.price_at_signal != None)   # noqa: E711
        )
        pending = result.scalars().all()
        logger.info(f"Backtest: evaluating {len(pending)} signals")

        for sig in pending:
            try:
                df = fetch_ohlcv(sig.symbol, sig.exchange, period="10d", interval="1d")
                if df is None or df.empty or sig.price_at_signal is None:
                    continue
                current_price = float(df["close"].iloc[-1])
                entry = sig.price_at_signal
                ret = (current_price - entry) / entry  # raw decimal return

                # Correct if direction matches return sign with min 0.5% move
                is_correct: bool
                if sig.direction == 1:
                    is_correct = ret > 0.005
                elif sig.direction == -1:
                    is_correct = ret < -0.005
                else:
                    is_correct = abs(ret) < 0.005

                sig.actual_return_5d = round(ret, 6)
                sig.backtest_correct = is_correct
                logger.info(
                    f"  {sig.symbol}: entry={entry:.2f} now={current_price:.2f} "
                    f"ret={ret:.2%} {'✅' if is_correct else '❌'}"
                )
            except Exception as e:
                logger.error(f"Backtest eval error for {sig.symbol}: {e}")

        await session.commit()
    logger.info("Backtest evaluation complete")


def setup_scheduler():
    """Register all jobs and start the scheduler."""

    # Kite daily login — 08:00 IST (before market open at 09:15)
    scheduler.add_job(
        job_kite_daily_login,
        CronTrigger(hour=8, minute=0, timezone="Asia/Kolkata"),
        id="kite_login",
        max_instances=1,
        replace_existing=True,
    )

    # EOD OHLCV — 16:30 IST (after NSE close)
    scheduler.add_job(
        job_fetch_eod_ohlcv,
        CronTrigger(hour=16, minute=30, timezone="Asia/Kolkata"),
        id="eod_ohlcv",
        max_instances=1,
        replace_existing=True,
    )

    # US EOD — 02:30 IST (after NYSE close at 4pm ET)
    scheduler.add_job(
        job_fetch_eod_ohlcv,
        CronTrigger(hour=2, minute=30, timezone="Asia/Kolkata"),
        id="us_eod_ohlcv",
        max_instances=1,
        replace_existing=True,
    )

    # News + sentiment — every 2 hours
    scheduler.add_job(
        job_fetch_and_score_news,
        IntervalTrigger(hours=2),
        id="news_sentiment",
        max_instances=1,
        replace_existing=True,
    )

    # Signal generation — 17:00 IST (after EOD data ready)
    scheduler.add_job(
        job_generate_signals,
        CronTrigger(hour=17, minute=0, timezone="Asia/Kolkata"),
        id="signal_gen",
        max_instances=1,
        replace_existing=True,
    )

    # Backtest evaluation — nightly 23:00 IST
    scheduler.add_job(
        job_backtest_evaluate,
        CronTrigger(hour=23, minute=0, timezone="Asia/Kolkata"),
        id="backtest_eval",
        max_instances=1,
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started with all jobs")
