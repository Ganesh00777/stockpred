"""
GitHub Actions ingest job — runs daily to fetch OHLCV and write to Supabase candles table.
Runs on GitHub's IPs (not blocked by Yahoo Finance).

Required environment variables (set as GitHub Actions secrets):
  SUPABASE_URL   — e.g. https://gfnafkddhhrjfhwlufwf.supabase.co
  SUPABASE_KEY   — service role key from Supabase → Settings → API Keys → Secret key
"""
import os
import sys
import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
from supabase import create_client, Client

# Disable yfinance SQLite cache — avoids "database is locked" on GitHub Actions
yf.set_tz_cache_location("/tmp/yfinance_tz")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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

PERIOD = "1y"


# ---------------------------------------------------------------------------
# Fetch per-symbol (more reliable than batch for multi-index parsing)
# ---------------------------------------------------------------------------
def fetch_symbol(ticker: str, symbol: str, exchange: str) -> pd.DataFrame:
    try:
        t = yf.Ticker(ticker)
        df = t.history(period=PERIOD, interval="1d", auto_adjust=True)
        if df is None or df.empty:
            logger.warning("No data for %s", ticker)
            return pd.DataFrame()

        df = df.reset_index()
        df.columns = [c.lower() for c in df.columns]
        df = df.rename(columns={"date": "ts", "datetime": "ts"})

        # Strip timezone from ts
        if "ts" in df.columns:
            df["ts"] = pd.to_datetime(df["ts"])
            if hasattr(df["ts"].dt, "tz") and df["ts"].dt.tz is not None:
                df["ts"] = df["ts"].dt.tz_localize(None)

        df["symbol"] = symbol
        df["exchange"] = exchange
        df["interval"] = "1d"

        cols = ["ts", "symbol", "exchange", "interval", "open", "high", "low", "close", "volume"]
        df = df[[c for c in cols if c in df.columns]].dropna(subset=["close"])
        logger.info("  %s: %d rows", symbol, len(df))
        return df

    except Exception as e:
        logger.warning("Failed %s: %s", ticker, e)
        return pd.DataFrame()


def fetch_group(tickers: list[str], symbols: list[str], exchange: str) -> pd.DataFrame:
    logger.info("Fetching %d %s tickers...", len(tickers), exchange)
    frames = []
    for ticker, symbol in zip(tickers, symbols):
        df = fetch_symbol(ticker, symbol, exchange)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Upsert to Supabase
# ---------------------------------------------------------------------------
def upsert_candles(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"]).dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    df["volume"] = df["volume"].fillna(0).astype(int)

    records = df.to_dict(orient="records")
    batch_size = 500
    total = 0

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        try:
            supabase.table("candles").upsert(
                batch,
                on_conflict="symbol,exchange,interval,ts",
            ).execute()
            total += len(batch)
            logger.info("  Upserted batch %d-%d", i, i + len(batch))
        except Exception as e:
            logger.error("Upsert failed for batch %d: %s", i, e)

    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    logger.info("=== StockPred candle ingest starting ===")
    logger.info("Time: %s", datetime.now(timezone.utc).isoformat())

    total_rows = 0
    errors = 0

    nse_tickers = [f"{s}.NS" for s in NSE_WATCHLIST]
    nse_df = fetch_group(nse_tickers, NSE_WATCHLIST, "NSE")
    if not nse_df.empty:
        n = upsert_candles(nse_df)
        total_rows += n
        logger.info("NSE: upserted %d rows", n)
    else:
        logger.error("NSE fetch returned no data")
        errors += 1

    us_df = fetch_group(US_WATCHLIST, US_WATCHLIST, "NASDAQ")
    if not us_df.empty:
        n = upsert_candles(us_df)
        total_rows += n
        logger.info("US: upserted %d rows", n)
    else:
        logger.error("US fetch returned no data")
        errors += 1

    logger.info("=== Done: %d total rows upserted, %d errors ===", total_rows, errors)

    if errors > 0 and total_rows == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
