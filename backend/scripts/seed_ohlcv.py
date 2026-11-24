"""
Seed historical OHLCV data into TimescaleDB (1 year back).
Run once after migrate.py:

    python scripts/seed_ohlcv.py
"""
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    from app.db.database import async_session
    from app.db.models import Candle
    from app.services.data_fetcher import fetch_all_ohlcv
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    logger.info("Fetching 1 year OHLCV for all watchlist stocks...")
    df = fetch_all_ohlcv(period="1y")

    if df.empty:
        logger.error("No data fetched — check yfinance connectivity")
        return

    logger.info("Fetched %d candles — inserting into DB...", len(df))

    records = df.to_dict(orient="records")
    batch_size = 500

    async with async_session() as session:
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            stmt = pg_insert(Candle).values(batch).on_conflict_do_nothing(
                index_elements=["symbol", "exchange", "interval", "ts"]
            )
            await session.execute(stmt)
            await session.commit()
            logger.info("Inserted batch %d/%d", i // batch_size + 1, (len(records) // batch_size) + 1)

    logger.info("Seed complete — %d candles inserted 🎉", len(records))


if __name__ == "__main__":
    asyncio.run(main())
