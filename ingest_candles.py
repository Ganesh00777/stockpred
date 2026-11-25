"""
GitHub Actions ingest job — runs daily to fetch OHLCV and write to Supabase candles table.
Runs on GitHub's IPs (not blocked by Yahoo Finance).

Required environment variables (set as GitHub Actions secrets):
  SUPABASE_URL   — e.g. https://gfnafkddhhrjfhwlufwf.supabase.co
  SUPABASE_KEY   — service role key (not anon key) from Supabase → Settings → API
"""
import os
import sys
import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
from supabase import create_client, Client

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

PERIOD = "1y"  # fetch last 1 year — Supabase upsert handles duplicates


# ---------------------------------------------------------------------------
# Fetch via yfinance batch download
# ---------------------------------------------------------------------------
def fetch_group(tickers: list[str], symbols: list[str], exchange: str) -> pd.DataFrame:
    logger.info("Downloading %d %s tickers...", len(tickers), exchange)
    try:
        raw = yf.download(
            tickers=tickers,
            period=PERIOD,
            interval="1d",
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            progress=False,
        )
    except Exception as e:
        logger.error("yf.download failed for %s: %s", exchange, e)
        return pd.DataFrame()

    if raw is None or raw.empty:
        logger.warning("Empty result for %s", exchange)
        return pd.DataFrame()

    frames = []
    for ticker, symbol in zip(tickers, symbols):
        try:
            if len(tickers) == 1:
                df = raw.copy()
            else:
                if ticker not in raw.columns.get_level_values(1):
                    logger.warning("No data for %s", ticker)
                    continue
                df = raw.xs(ticker, axis=1, level=1).copy()

            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            df = df.rename(columns={"date": "ts", "datetime": "ts"})
            df["symbol"] = symbol
            df["exchange"] = exchange
            df["interval"] = "1d"

            cols = ["ts", "symbol", "exchange", "interval", "open", "high", "low", "close", "volume"]
            df = df[[c for c in cols if c in df.columns]].dropna(subset=["close"])

            # Strip timezone
            if hasattr(df["ts"].dtype, "tz") and df["ts"].dt.tz is not None:
                df["ts"] = df["ts"].dt.tz_localize(None)

            if not df.empty:
                logger.info("  %s: %d rows", symbol, len(df))
                frames.append(df)
        except Exception as e:
            logger.warning("Parse failed for %s: %s", ticker, e)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Upsert to Supabase
# ---------------------------------------------------------------------------
def upsert_candles(df: pd.DataFrame) -> int:
    if df.empty:
        return 0

    # Convert timestamps to ISO strings for JSON serialization
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"]).dt.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    df["volume"] = df["volume"].fillna(0).astype(int)

    records = df.to_dict(orient="records")
    batch_size = 500
    total = 0

    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        try:
            # upsert on (symbol, exchange, interval, ts)
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

    # NSE batch
    nse_tickers = [f"{s}.NS" for s in NSE_WATCHLIST]
    nse_df = fetch_group(nse_tickers, NSE_WATCHLIST, "NSE")
    if not nse_df.empty:
        n = upsert_candles(nse_df)
        total_rows += n
        logger.info("NSE: upserted %d rows", n)
    else:
        logger.error("NSE fetch returned no data")
        errors += 1

    # US batch
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
        sys.exit(1)  # Fail the GitHub Action if everything failed


if __name__ == "__main__":
    main()
