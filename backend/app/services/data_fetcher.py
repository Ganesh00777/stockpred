"""
Data ingestion: market OHLCV + volume data.
Reads from Supabase `candles` table — populated daily by GitHub Actions ingest job.
No live Yahoo Finance calls from Railway (IPs are blocked by Yahoo).
Per-symbol in-memory cache with 1-hour TTL.
"""
import logging
import time
import threading
from typing import List, Optional, Dict

import pandas as pd
from supabase import create_client, Client

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supabase client (uses existing SUPABASE_URL + SUPABASE_KEY env vars)
# ---------------------------------------------------------------------------
_supabase: Optional[Client] = None
_supabase_lock = threading.Lock()


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        with _supabase_lock:
            if _supabase is None:
                _supabase = create_client(
                    settings.SUPABASE_URL,
                    settings.SUPABASE_KEY,
                )
    return _supabase


# ---------------------------------------------------------------------------
# In-memory cache  (key → (DataFrame, timestamp))
# ---------------------------------------------------------------------------
_cache_lock = threading.Lock()
_ohlcv_cache: Dict[str, tuple] = {}
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
        return df.copy()


def _cache_set(key: str, df: pd.DataFrame) -> None:
    with _cache_lock:
        _ohlcv_cache[key] = (df.copy(), time.time())


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
# Fetch from Supabase candles table
# ---------------------------------------------------------------------------
def _fetch_from_db(symbol: str, exchange: str, period: str = "1y") -> pd.DataFrame:
    """
    Query candles table for a single symbol/exchange.
    period: '3mo' or '1y' — converted to a date cutoff.
    """
    # Convert period string to days
    period_days = {"3mo": 90, "6mo": 180, "1y": 365, "2y": 730}.get(period, 365)

    try:
        sb = _get_supabase()
        # Supabase postgrest: filter ts >= now - period_days
        from datetime import datetime, timedelta, timezone
        cutoff = (datetime.now(timezone.utc) - timedelta(days=period_days)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

        response = (
            sb.table("candles")
            .select("ts,open,high,low,close,volume,symbol,exchange,interval")
            .eq("symbol", symbol)
            .eq("exchange", exchange)
            .eq("interval", "1d")
            .gte("ts", cutoff)
            .order("ts")
            .execute()
        )

        rows = response.data
        if not rows:
            logger.warning("No candles in DB for %s/%s", symbol, exchange)
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["ts"] = pd.to_datetime(df["ts"])
        df["close"] = df["close"].astype(float)
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["volume"] = df["volume"].astype(float)
        df = df.sort_values("ts").reset_index(drop=True)
        logger.debug("DB fetch %s/%s: %d rows", symbol, exchange, len(df))
        return df

    except Exception as e:
        logger.error("DB fetch failed for %s/%s: %s", symbol, exchange, e)
        return pd.DataFrame()


def _get_nse_data(period: str = "3mo") -> Dict[str, pd.DataFrame]:
    """Return NSE data dict from cache or Supabase."""
    all_data = {}
    for symbol in NSE_WATCHLIST:
        cache_key = f"{symbol}:NSE:{period}"
        df = _cache_get(cache_key)
        if df is None:
            df = _fetch_from_db(symbol, "NSE", period)
            if not df.empty:
                _cache_set(cache_key, df)
        if not df.empty:
            all_data[symbol] = df
    return all_data


def _get_us_data(period: str = "3mo") -> Dict[str, pd.DataFrame]:
    """Return US data dict from cache or Supabase."""
    all_data = {}
    for symbol in US_WATCHLIST:
        cache_key = f"{symbol}:NASDAQ:{period}"
        df = _cache_get(cache_key)
        if df is None:
            df = _fetch_from_db(symbol, "NASDAQ", period)
            if not df.empty:
                _cache_set(cache_key, df)
        if not df.empty:
            all_data[symbol] = df
    return all_data


# ---------------------------------------------------------------------------
# Public API  (same interface as before — callers unchanged)
# ---------------------------------------------------------------------------
def fetch_ohlcv(symbol: str, exchange: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Fetch OHLCV for a single symbol from Supabase candles table."""
    if exchange == "NSE":
        data = _get_nse_data(period=period)
    else:
        data = _get_us_data(period=period)
    return data.get(symbol)


def fetch_all_ohlcv(period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV for all watchlist stocks from Supabase."""
    nse_data = _get_nse_data(period=period)
    us_data = _get_us_data(period=period)
    all_data = {**nse_data, **us_data}
    if not all_data:
        logger.error("No candle data in DB — has the GitHub Actions ingest run yet?")
        return pd.DataFrame()
    result = pd.concat(all_data.values(), ignore_index=True)
    logger.info("Total candles from DB: %d", len(result))
    return result


# ---------------------------------------------------------------------------
# Volume surge candidates  (same interface as before)
# ---------------------------------------------------------------------------
_CANDIDATES_CACHE: Optional[List[dict]] = None
_CANDIDATES_CACHE_TIME = 0.0
_CANDIDATES_CACHE_TTL = 3600  # 1 hour


def _refresh_candidates_cache(min_ratio: float = 2.0) -> List[dict]:
    """Compute volume surge candidates from Supabase candles data."""
    global _CANDIDATES_CACHE, _CANDIDATES_CACHE_TIME
    candidates = []

    nse_data = _get_nse_data(period="3mo")
    us_data = _get_us_data(period="3mo")

    for symbol, df in {**nse_data, **us_data}.items():
        exchange = "NSE" if symbol in NSE_WATCHLIST else "NASDAQ"
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
    Returns stocks where today's volume >= min_ratio * 20-day avg.
    Reads from Supabase candles table. 1-hour in-memory cache.
    """
    global _CANDIDATES_CACHE, _CANDIDATES_CACHE_TIME

    now = time.time()
    if _CANDIDATES_CACHE is not None and (now - _CANDIDATES_CACHE_TIME) < _CANDIDATES_CACHE_TTL:
        logger.debug("Returning cached volume surge candidates")
        return _CANDIDATES_CACHE

    logger.info("Refreshing volume surge candidates from DB...")
    return _refresh_candidates_cache(min_ratio)
