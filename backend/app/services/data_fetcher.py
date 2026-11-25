"""
Data ingestion: market OHLCV + volume data from yfinance with browser headers.
Uses yfinance with a custom requests session to avoid Yahoo IP blocks on Railway.
"""
import logging
import time
import random

_AV_DELAY = 0  # unused, kept for safety
from typing import List, Optional
import pandas as pd
import requests
import yfinance as yf

from app.core.config import settings

logger = logging.getLogger(__name__)

# Browser-like headers to avoid Yahoo blocking datacenter IPs
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}

def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_HEADERS)
    return session

# NSE symbols to track (expand as needed)
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

def _yf_symbol(symbol: str, exchange: str) -> str:
    """Convert symbol to yfinance format."""
    return f"{symbol}.NS" if exchange == "NSE" else symbol


def _fetch_nse_ohlcv(symbol: str, period: str = "1y") -> Optional[pd.DataFrame]:
    """Fetch NSE OHLCV via yfinance .NS suffix with retry."""
    ticker_sym = f"{symbol}.NS"
    for attempt in range(3):
        try:
            time.sleep(random.uniform(1, 3))
            session = _make_session()
            ticker = yf.Ticker(ticker_sym, session=session)
            df = ticker.history(period=period, interval="1d", auto_adjust=True)
            if df.empty:
                continue
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            df = df.rename(columns={"date": "ts", "datetime": "ts"})
            df["symbol"] = symbol
            df["exchange"] = "NSE"
            df["interval"] = "1d"
            df = df[["ts", "symbol", "exchange", "interval", "open", "high", "low", "close", "volume"]]
            if hasattr(df["ts"].dtype, "tz") and df["ts"].dt.tz is not None:
                df["ts"] = df["ts"].dt.tz_localize(None)
            return df.dropna()
        except Exception as e:
            logger.warning("yfinance attempt %d failed for %s: %s", attempt+1, ticker_sym, e)
    return None


def fetch_ohlcv(symbol: str, exchange: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV — NSE India API for NSE stocks, yfinance for US stocks.
    """
    if exchange == "NSE":
        df = _fetch_nse_ohlcv(symbol, period)
        if df is not None:
            return df
        logger.warning("NSE API failed for %s, skipping", symbol)
        return None

    # US stocks — yfinance
    ticker_sym = _yf_symbol(symbol, exchange)
    time.sleep(random.uniform(0.5, 1.5))
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
        if hasattr(df["ts"].dtype, "tz") and df["ts"].dt.tz is not None:
            df["ts"] = df["ts"].dt.tz_localize(None)
        return df.dropna()
    except Exception as e:
        logger.error("Error fetching %s: %s", ticker_sym, e)
        return None

def fetch_all_ohlcv(period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV for all watchlist stocks via yfinance with browser session."""
    frames = []
    total = len(NSE_WATCHLIST) + len(US_WATCHLIST)
    count = 0

    for symbol in NSE_WATCHLIST:
        count += 1
        logger.info("[%d/%d] Fetching %s NSE...", count, total, symbol)
        df = fetch_ohlcv(symbol, "NSE", period=period)
        if df is not None:
            frames.append(df)
            logger.info("  → %d rows", len(df))
        else:
            logger.warning("  → skipped (no data)")

    for symbol in US_WATCHLIST:
        count += 1
        logger.info("[%d/%d] Fetching %s NASDAQ...", count, total, symbol)
        df = fetch_ohlcv(symbol, "NASDAQ", period=period)
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


def fetch_volume_surge_candidates(min_ratio: float = 2.0) -> List[dict]:
    """
    Returns stocks where today's volume >= min_ratio * 20d avg volume.
    This is the primary breakout screen.
    """
    candidates = []
    all_symbols = [(s, "NSE") for s in NSE_WATCHLIST] + [(s, "NASDAQ") for s in US_WATCHLIST]

    for symbol, exchange in all_symbols:
        df = fetch_ohlcv(symbol, exchange, period="3mo", interval="1d")
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

    return sorted(candidates, key=lambda x: x["volume_ratio"], reverse=True)