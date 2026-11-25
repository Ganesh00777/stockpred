"""
Data ingestion: market OHLCV + volume data.
Uses yfinance for both NSE (.NS suffix) and US stocks — works from Railway.
Per-symbol in-memory cache with 1-hour TTL to avoid rate limits.
"""
import logging
import time
import random
import threading
from typing import List, Optional

import pandas as pd
import requests
import yfinance as yf

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-symbol OHLCV cache  (key → (DataFrame, timestamp))
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_ohlcv_cache: dict = {}
_CACHE_TTL = 3600  # 1 hour


def _cache_get(key: str) -> Optional[pd.DataFrame]:
    with _cache_lock:
        entry = _ohlcv_cache.get(key)
        if entry is None:
            return None
        df, ts = entry
        if time.time() - ts > _CACHE_TTL:
            del _ohlcv_cache[key]
            return None
        return df


def _cache_set(key: str, df: pd.DataFrame) -> None:
    with _cache_lock:
        _ohlcv_cache[key] = (df, time.time())


# ---------------------------------------------------------------------------
# Watchlists
# ---------------------------------------------------------------------------
NSE_WATCHLIST = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN",
    "SUNPHARMA", "WIPRO", "ULTRACEMCO", "BAJFINANCE", "NESTLEIND",
    "POWERGRID", "NTPC", "TECHM", "HCLTECH", "DIVISLAB",
    "TATASTEEL", "JSWSTEEL", "HINDALCO", "COALINDIA", "ONGC",
    "ADANIPORTS", "BAJAJFINSV", "DRREDDY", "CIPLA", "EICHERMOT",
    "GRASIM", "INDUSINDBK", "BPCL", "TATACONSUM", "BRITANNIA",
]

US_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "META",
    "AMZN", "TSLA", "AMD", "NFLX", "PLTR",
]

# ---------------------------------------------------------------------------
# Browser-like session to reduce Yahoo Finance blocking
# ---------------------------------------------------------------------------
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_HEADERS)
    return session


# ---------------------------------------------------------------------------
# Core yfinance fetch (NSE and US)
# ---------------------------------------------------------------------------
def _fetch_yfinance(ticker_sym: str, symbol: str, exchange: str,
                    period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Fetch OHLCV via yfinance. Works for both .NS (NSE) and plain US tickers."""
    time.sleep(random.uniform(0.3, 0.8))
    try:
        session = _make_session()
        ticker = yf.Ticker(ticker_sym, session=session)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            logger.warning("No data returned for %s", ticker_sym)
            return None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"date": "ts", "datetime": "ts"})
        df["symbol"] = symbol
        df["exchange"] = exchange
        df["interval"] = interval
        df = df[["ts", "symbol", "exchange", "interval", "open", "high", "low", "close", "volume"]]
        # Strip timezone info
        if hasattr(df["ts"].dtype, "tz") and df["ts"].dt.tz is not None:
            df["ts"] = df["ts"].dt.tz_localize(None)
        return df.dropna()
    except Exception as e:
        logger.error("yfinance failed for %s: %s", ticker_sym, e)
        return None


# ---------------------------------------------------------------------------
# Public fetch functions
# ---------------------------------------------------------------------------
def fetch_ohlcv(symbol: str, exchange: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Fetch OHLCV. NSE → yfinance with .NS suffix. US → yfinance plain."""
    if exchange == "NSE":
        ticker_sym = f"{symbol}.NS"
    else:
        ticker_sym = symbol
    return _fetch_yfinance(ticker_sym, symbol, exchange, period, interval)


def _cached_fetch_ohlcv(symbol: str, exchange: str, period: str = "3mo") -> Optional[pd.DataFrame]:
    """
    Fetch with 1-hour in-memory cache.
    Returns cached data if fresh; otherwise fetches from Yahoo Finance.
    Small random delay to avoid hammering Yahoo on cold start.
    """
    cache_key = f"{symbol}:{exchange}:{period}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("Cache hit for %s", cache_key)
        return cached

    df = fetch_ohlcv(symbol, exchange, period=period)
    if df is not None:
        _cache_set(cache_key, df)
    return df


# ---------------------------------------------------------------------------
# fetch_all_ohlcv  (used by DB ingest job — not called on every request)
# ---------------------------------------------------------------------------
def fetch_all_ohlcv(period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV for all watchlist stocks. Run as a background job."""
    frames = []
    total = len(NSE_WATCHLIST) + len(US_WATCHLIST)
    count = 0

    for symbol in NSE_WATCHLIST:
        count += 1
        logger.info("[%d/%d] Fetching %s NSE...", count, total, symbol)
        df = _cached_fetch_ohlcv(symbol, "NSE", period=period)
        if df is not None:
            frames.append(df)
            logger.info("  → %d rows", len(df))
        else:
            logger.warning("  → skipped (no data)")

    for symbol in US_WATCHLIST:
        count += 1
        logger.info("[%d/%d] Fetching %s NASDAQ...", count, total, symbol)
        df = _cached_fetch_ohlcv(symbol, "NASDAQ", period=period)
        if df is not None:
            frames.append(df)
            logger.info("  → %d rows", len(df))
        else:
            logger.warning("  → skipped (no data)")

    if not frames:
        logger.error("No data fetched — check yfinance connectivity")
        return pd.DataFrame()

    result = pd.concat(frames, ignore_index=True)
    logger.info("Total candles fetched: %d", len(result))
    return result


# ---------------------------------------------------------------------------
# Volume surge candidates  (cached at the candidates level too)
# ---------------------------------------------------------------------------
_CANDIDATES_CACHE: Optional[List[dict]] = None
_CANDIDATES_CACHE_TIME = 0.0
_CANDIDATES_CACHE_TTL = 3600  # 1 hour


def _refresh_candidates_cache(min_ratio: float = 2.0) -> List[dict]:
    """Fetch volume surge candidates using per-symbol cache to avoid rate limits."""
    global _CANDIDATES_CACHE, _CANDIDATES_CACHE_TIME
    candidates = []
    all_symbols = [(s, "NSE") for s in NSE_WATCHLIST] + [(s, "NASDAQ") for s in US_WATCHLIST]

    for symbol, exchange in all_symbols:
        df = _cached_fetch_ohlcv(symbol, exchange, period="3mo")
        if df is None or len(df) < 21:
            continue

        df = df.sort_values("ts")
        avg_vol_20d = df["volume"].iloc[-21:-1].mean()
        today_vol = df["volume"].iloc[-1]

        if avg_vol_20d == 0:
            continue

        ratio = today_vol / avg_vol_20d
        if ratio >= min_ratio:
            candidates.append({
                "symbol": symbol,
                "exchange": exchange,
                "today_volume": int(today_vol),
                "avg_volume_20d": int(avg_vol_20d),
                "volume_ratio": round(ratio, 2),
                "close": float(df["close"].iloc[-1]),
                "pct_change": round(
                    (df["close"].iloc[-1] - df["close"].iloc[-2]) / df["close"].iloc[-2] * 100, 2
                ),
            })

    _CANDIDATES_CACHE = sorted(candidates, key=lambda x: x["volume_ratio"], reverse=True)
    _CANDIDATES_CACHE_TIME = time.time()
    return _CANDIDATES_CACHE


def fetch_volume_surge_candidates(min_ratio: float = 2.0) -> List[dict]:
    """
    Returns stocks where today's volume >= min_ratio * 20-day avg volume.
    Uses 1-hour candidates cache. Each symbol is also individually cached,
    so repeated /signals calls don't re-hit Yahoo Finance.
    """
    global _CANDIDATES_CACHE, _CANDIDATES_CACHE_TIME

    now = time.time()
    if _CANDIDATES_CACHE is not None and (now - _CANDIDATES_CACHE_TIME) < _CANDIDATES_CACHE_TTL:
        logger.debug("Returning cached volume surge candidates")
        return _CANDIDATES_CACHE

    logger.info("Refreshing volume surge candidates cache...")
    return _refresh_candidates_cache(min_ratio)
