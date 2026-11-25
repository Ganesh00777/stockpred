"""
One-shot DB migration: creates all tables.
Optionally enables TimescaleDB hypertable if the extension is available.

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


async def try_timescale(session):
    """Try to enable TimescaleDB hypertable — skip gracefully if unavailable."""
    try:
        from sqlalchemy import text
        # Check if extension exists first
        result = await session.execute(
            text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")
        )
        if result.scalar():
            await session.execute(
                text(
                    "SELECT create_hypertable('candles', 'ts', "
                    "if_not_exists => TRUE, "
                    "chunk_time_interval => INTERVAL '1 day');"
                )
            )
            await session.commit()
            logger.info("TimescaleDB hypertable enabled on candles ✅")
        else:
            logger.warning(
                "TimescaleDB extension not found — skipping hypertable. "
                "Plain Postgres indexes will be used instead (fine for < 1M rows)."
            )
    except Exception as e:
        logger.warning(f"TimescaleDB setup skipped: {e}")


async def main():
    from app.db.database import create_all_tables, AsyncSessionLocal, async_engine
    from app.db import models  # noqa — ensure models are imported

    logger.info("Creating all tables...")
    await create_all_tables()
    logger.info("Tables created ✅")

    async with AsyncSessionLocal() as session:
        await try_timescale(session)

    logger.info("Migration complete 🎉")
    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
