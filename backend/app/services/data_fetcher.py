"""
Data ingestion: market OHLCV + volume data.
Uses yfinance batch download to fetch all symbols in one HTTP call per group —
avoids per-symbol rate limiting that blocks Railway datacenter IPs.
Per-group in-memory cache with 1-hour TTL.
"""
import logging
import time
import threading
from typing import List, Optional, Dict

import pandas as pd
import requests
import yfinance as yf

from app.core.config import settings

logger = logging.getLogger(__name__)

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

# yfinance tickers for NSE
NSE_TICKERS = [f"{s}.NS" for s in NSE_WATCHLIST]
US_TICKERS = list(US_WATCHLIST)

# ---------------------------------------------------------------------------
# Batch download via yf.download()
# Fetches all symbols in ONE HTTP request — avoids per-IP rate limits
# ---------------------------------------------------------------------------

def _batch_download(tickers: List[str], period: str = "3mo") -> pd.DataFrame:
    """
    Download OHLCV for all tickers in one batch call.
    Returns a flat DataFrame with columns: ts, symbol, exchange, interval,
    open, high, low, close, volume.
    """
    try:
        raw = yf.download(
            tickers=tickers,
            period=period,
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            progress=False,
        )
        if raw is None or raw.empty:
            logger.warning("yf.download returned empty for %s tickers", len(tickers))
            return pd.DataFrame()
        return raw
    except Exception as e:
        logger.error("yf.download failed: %s", e)
        return pd.DataFrame()


def _parse_batch(raw: pd.DataFrame, tickers: List[str], symbols: List[str],
                 exchange: str) -> Dict[str, pd.DataFrame]:
    """
    Parse yf.download() multi-ticker result into per-symbol DataFrames.
    Returns dict: symbol → DataFrame
    """
    result = {}
    if raw.empty:
        return result

    for ticker, symbol in zip(tickers, symbols):
        try:
            # Multi-ticker download uses MultiIndex columns: (field, ticker)
            if len(tickers) == 1:
                df = raw.copy()
            else:
                if ticker not in raw.columns.get_level_values(1):
                    continue
                df = raw.xs(ticker, axis=1, level=1).copy()

            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            df = df.rename(columns={"date": "ts", "datetime": "ts"})
            df["symbol"] = symbol
            df["exchange"] = exchange
            df["interval"] = "1d"

            cols = ["ts", "symbol", "exchange", "interval", "open", "high", "low", "close", "volume"]
            available = [c for c in cols if c in df.columns]
            df = df[available].dropna(subset=["close"])

            # Strip timezone
            if "ts" in df.columns:
                ts_col = df["ts"]
                if hasattr(ts_col.dtype, "tz") and ts_col.dt.tz is not None:
                    df["ts"] = ts_col.dt.tz_localize(None)

            if not df.empty:
                result[symbol] = df.sort_values("ts").reset_index(drop=True)
        except Exception as e:
            logger.warning("Parse failed for %s: %s", symbol, e)

    return result


# ---------------------------------------------------------------------------
# Cached group-level fetch
# ---------------------------------------------------------------------------
def _get_nse_data(period: str = "3mo") -> Dict[str, pd.DataFrame]:
    """Return NSE data dict from cache or fresh batch download."""
    cache_key = f"batch:NSE:{period}"
    cached = _cache_get(cache_key)
    if cached is not None:
        # cached is a sentinel; actual data stored per-symbol
        pass

    # Check if we have all symbols cached individually
    all_cached = {}
    missing = []
    for symbol in NSE_WATCHLIST:
        sym_key = f"{symbol}:NSE:{period}"
        df = _cache_get(sym_key)
        if df is not None:
            all_cached[symbol] = df
        else:
            missing.append(symbol)

    if not missing:
        logger.debug("All NSE symbols in cache")
        return all_cached

    # Batch fetch missing symbols
    missing_tickers = [f"{s}.NS" for s in missing]
    logger.info("Batch downloading %d NSE symbols via yf.download...", len(missing_tickers))
    raw = _batch_download(missing_tickers, period=period)
    parsed = _parse_batch(raw, missing_tickers, missing, "NSE")

    for symbol, df in parsed.items():
        _cache_set(f"{symbol}:NSE:{period}", df)
        all_cached[symbol] = df

    for symbol in missing:
        if symbol not in parsed:
            logger.warning("No data for %s.NS", symbol)

    return all_cached


def _get_us_data(period: str = "3mo") -> Dict[str, pd.DataFrame]:
    """Return US data dict from cache or fresh batch download."""
    all_cached = {}
    missing = []
    for symbol in US_WATCHLIST:
        sym_key = f"{symbol}:NASDAQ:{period}"
        df = _cache_get(sym_key)
        if df is not None:
            all_cached[symbol] = df
        else:
            missing.append(symbol)

    if not missing:
        logger.debug("All US symbols in cache")
        return all_cached

    logger.info("Batch downloading %d US symbols via yf.download...", len(missing))
    raw = _batch_download(missing, period=period)
    parsed = _parse_batch(raw, missing, missing, "NASDAQ")

    for symbol, df in parsed.items():
        _cache_set(f"{symbol}:NASDAQ:{period}", df)
        all_cached[symbol] = df

    return all_cached


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_ohlcv(symbol: str, exchange: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """Fetch OHLCV for a single symbol (uses batch cache under the hood)."""
    if exchange == "NSE":
        data = _get_nse_data(period=period)
    else:
        data = _get_us_data(period=period)
    return data.get(symbol)


def fetch_all_ohlcv(period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV for all watchlist stocks."""
    nse_data = _get_nse_data(period=period)
    us_data = _get_us_data(period=period)
    all_data = {**nse_data, **us_data}
    if not all_data:
        logger.error("No data fetched — check yfinance connectivity")
        return pd.DataFrame()
    result = pd.concat(all_data.values(), ignore_index=True)
    logger.info("Total candles fetched: %d", len(result))
    return result


# ---------------------------------------------------------------------------
# Volume surge candidates  (cached at the candidates level too)
# ---------------------------------------------------------------------------
_CANDIDATES_CACHE: Optional[List[dict]] = None
_CANDIDATES_CACHE_TIME = 0.0
_CANDIDATES_CACHE_TTL = 3600  # 1 hour


def _refresh_candidates_cache(min_ratio: float = 2.0) -> List[dict]:
    """Compute volume surge candidates from batch-cached data."""
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
    Backed by 1-hour cache. Uses batch download — only 2 HTTP requests
    total (one for NSE, one for US) instead of 50 individual calls.
    """
    global _CANDIDATES_CACHE, _CANDIDATES_CACHE_TIME

    now = time.time()
    if _CANDIDATES_CACHE is not None and (now - _CANDIDATES_CACHE_TIME) < _CANDIDATES_CACHE_TTL:
        logger.debug("Returning cached volume surge candidates")
        return _CANDIDATES_CACHE

    logger.info("Refreshing volume surge candidates cache...")
    return _refresh_candidates_cache(min_ratio)
