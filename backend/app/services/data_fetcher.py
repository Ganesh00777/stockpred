"""
Data ingestion: market OHLCV + volume data from yfinance / Kite.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional
import pandas as pd
import yfinance as yf
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

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


def nse_to_yf(symbol: str) -> str:
    """Convert NSE symbol to yfinance format."""
    return f"{symbol}.NS"


def fetch_ohlcv(symbol: str, exchange: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data from yfinance.
    Returns DataFrame with columns: ts, open, high, low, close, volume
    """
    try:
        ticker = nse_to_yf(symbol) if exchange == "NSE" else symbol
        df = yf.download(ticker, period=period, interval=interval,
                         auto_adjust=True, progress=False)
        if df.empty:
            logger.warning(f"No data returned for {ticker}")
            return None

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"date": "ts", "datetime": "ts"})
        df["symbol"] = symbol
        df["exchange"] = exchange
        df["interval"] = interval
        df = df[["ts", "symbol", "exchange", "interval",
                  "open", "high", "low", "close", "volume"]]
        df = df.dropna()
        return df

    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        return None


def fetch_all_ohlcv(period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV for all watchlist stocks."""
    frames = []

    for symbol in NSE_WATCHLIST:
        df = fetch_ohlcv(symbol, "NSE", period=period)
        if df is not None:
            frames.append(df)
            logger.info(f"Fetched {symbol} NSE: {len(df)} rows")

    for symbol in US_WATCHLIST:
        df = fetch_ohlcv(symbol, "NASDAQ", period=period)
        if df is not None:
            frames.append(df)
            logger.info(f"Fetched {symbol} US: {len(df)} rows")

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


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
