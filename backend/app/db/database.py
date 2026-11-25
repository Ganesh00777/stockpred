from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine
from app.core.config import settings
from app.db.models import Base

# Async engine for FastAPI
async_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    echo=settings.APP_ENV == "development",
    connect_args={"statement_cache_size": 0},
    pool_pre_ping=True,       # test connection before using it
    pool_recycle=300,         # recycle connections every 5 min
)

engine = async_engine  # alias for backwards compat

AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Sync engine for migrations and ML jobs
sync_engine = create_engine(settings.SYNC_DATABASE_URL)


async def get_db():
    """FastAPI dependency — yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def create_all_tables():
    """Create all tables (dev/test only — use Alembic in production)."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def init_timescale(session: AsyncSession):
    """Convert candles table to a TimescaleDB hypertable."""
    await session.execute(
        "SELECT create_hypertable('candles', 'ts', if_not_exists => TRUE, "
        "chunk_time_interval => INTERVAL '1 day');"
    )
    await session.commit()
