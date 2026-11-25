"""
Data ingestion: market OHLCV + volume data.
Uses Twelve Data API for NSE stocks (works from Railway), yfinance for US stocks.
Per-symbol in-memory cache with 1-hour TTL to avoid Twelve Data rate limits.
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

# TCS trades on BSE, not NSE — Twelve Data returns 404 for TCS/NSE
_NSE_EXCHANGE_OVERRIDE = {
    "TCS": "BSE",
}

# ---------------------------------------------------------------------------
# Browser-like session for yfinance (US stocks)
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
# Twelve Data — NSE / BSE
# ---------------------------------------------------------------------------
def _fetch_nse_ohlcv(symbol: str, period: str = "1y") -> Optional[pd.DataFrame]:
    """Fetch NSE/BSE OHLCV via Twelve Data API (works from Railway)."""
    try:
        api_key = settings.TWELVE_DATA_API_KEY
        if not api_key:
            logger.warning("TWELVE_DATA_API_KEY not set")
            return None

        period_days = {"3mo": 90, "6mo": 180, "1y": 365, "2y": 730}
        outputsize = period_days.get(period, 365)
        exchange = _NSE_EXCHANGE_OVERRIDE.get(symbol, "NSE")

        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,       # e.g. "RELIANCE" (no suffix)
            "exchange": exchange,   # "NSE" or "BSE"
            "interval": "1day",
            "outputsize": outputsize,
            "apikey": api_key,
            "format": "JSON",
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") == "error":
            logger.warning("Twelve Data error for %s: %s", symbol, data.get("message"))
            return None

        values = data.get("values", [])
        if not values:
            return None

        rows = [{
            "ts": pd.to_datetime(d["datetime"]),
            "open": float(d["open"]),
            "high": float(d["high"]),
            "low": float(d["low"]),
            "close": float(d["close"]),
            "volume": int(d.get("volume", 0)),
            "symbol": symbol,
            "exchange": exchange,
            "interval": "1d",
        } for d in values]

        df = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
        return df

    except Exception as e:
        logger.warning("Twelve Data failed for %s: %s", symbol, e)
        return None


# ---------------------------------------------------------------------------
# yfinance — US stocks
# ---------------------------------------------------------------------------
def _fetch_us_ohlcv(symbol: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Fetch US stock OHLCV via yfinance (may be blocked on Railway IPs)."""
    time.sleep(random.uniform(0.5, 1.5))
    try:
        session = _make_session()
        ticker = yf.Ticker(symbol, session=session)
        df = ticker.history(period=period, interval=interval, auto_adjust=True)
        if df.empty:
            logger.warning("No data returned for %s", symbol)
            return None
        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"date": "ts", "datetime": "ts"})
        df["symbol"] = symbol
        df["exchange"] = "NASDAQ"
        df["interval"] = interval
        df = df[["ts", "symbol", "exchange", "interval", "open", "high", "low", "close", "volume"]]
        if hasattr(df["ts"].dtype, "tz") and df["ts"].dt.tz is not None:
            df["ts"] = df["ts"].dt.tz_localize(None)
        return df.dropna()
    except Exception as e:
        logger.error("yfinance failed for %s: %s", symbol, e)
        return None


# ---------------------------------------------------------------------------
# Public fetch with per-symbol cache + rate-limit delay
# ---------------------------------------------------------------------------
def fetch_ohlcv(symbol: str, exchange: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Fetch OHLCV. NSE/BSE → Twelve Data. US → yfinance."""
    if exchange == "NSE":
        df = _fetch_nse_ohlcv(symbol, period)
        if df is None:
            logger.warning("NSE API failed for %s, skipping", symbol)
        return df
    return _fetch_us_ohlcv(symbol, period, interval)


def _cached_fetch_ohlcv(symbol: str, exchange: str, period: str = "3mo") -> Optional[pd.DataFrame]:
    """
    Fetch with 1-hour in-memory cache.
    For NSE stocks, adds an 8-second delay before hitting the API
    to stay within Twelve Data's 8 req/min free-tier limit.
    """
    cache_key = f"{symbol}:{exchange}:{period}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug("Cache hit for %s", cache_key)
        return cached

    # Rate-limit delay only when we actually need to call the API
    if exchange == "NSE":
        time.sleep(8)

    df = fetch_ohlcv(symbol, exchange, period=period)
    if df is not None:
        _cache_set(cache_key, df)
    return df


# ---------------------------------------------------------------------------
# fetch_all_ohlcv  (used by DB ingest job — not called on every request)
# ---------------------------------------------------------------------------
def fetch_all_ohlcv(period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV for all watchlist stocks. Slow — run as a background job."""
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
        # _cached_fetch_ohlcv already sleeps 8s before an uncached NSE call

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
        logger.error("No data fetched — check API connectivity")
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
    """Fetch volume surge candidates using per-symbol cache to avoid 429s."""
    global _CANDIDATES_CACHE, _CANDIDATES_CACHE_TIME
    candidates = []
    all_symbols = [(s, "NSE") for s in NSE_WATCHLIST] + [(s, "NASDAQ") for s in US_WATCHLIST]

    for symbol, exchange in all_symbols:
        # _cached_fetch_ohlcv: returns from cache if fresh, otherwise fetches
        # with rate-limit delay (8s for NSE). Cache hit = no delay, no API call.
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
    so repeated /signals calls don't re-hit the API.
    """
    global _CANDIDATES_CACHE, _CANDIDATES_CACHE_TIME

    now = time.time()
    if _CANDIDATES_CACHE is not None and (now - _CANDIDATES_CACHE_TIME) < _CANDIDATES_CACHE_TTL:
        logger.debug("Returning cached volume surge candidates")
        return _CANDIDATES_CACHE

    logger.info("Refreshing volume surge candidates cache...")
    return _refresh_candidates_cache(min_ratio)
