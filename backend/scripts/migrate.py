"""
One-shot DB migration: creates all tables + TimescaleDB hypertable.
Run once after Supabase DB is provisioned:

    python scripts/migrate.py
"""
import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    from app.db.database import create_all_tables, init_timescale, engine
    from app.db import models  # noqa — ensure models are imported

    logger.info("Creating all tables...")
    await create_all_tables()
    logger.info("Tables created ✅")

    logger.info("Initialising TimescaleDB hypertable on candles...")
    await init_timescale()
    logger.info("TimescaleDB hypertable ready ✅")

    logger.info("Migration complete 🎉")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
