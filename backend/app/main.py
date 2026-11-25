"""FastAPI app entrypoint."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.db.database import create_all_tables, init_timescale
from app.services.scheduler import setup_scheduler, scheduler
from app.services.kite_ticker import get_ticker
from app.services.kite_auth import get_or_refresh_token

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("StockPred starting up...")

    # 1. Ensure DB tables + TimescaleDB hypertable exist
    try:
       ## await create_all_tables()
        await init_timescale()
        logger.info("DB ready ✅")
    except Exception as e:
        logger.error("DB init error (non-fatal): %s", e)

    # 2. Refresh Kite access token from Redis / auto-login
    try:
        token = get_or_refresh_token()
        if token:
            logger.info("Kite token loaded ✅")
        else:
            logger.warning("Kite token unavailable — using yfinance fallback")
    except Exception as e:
        logger.warning("Kite token refresh error: %s", e)

    # 3. Start Kite WebSocket ticker
    try:
        get_ticker().start()
        logger.info("Kite ticker started ✅")
    except Exception as e:
        logger.warning("Kite ticker start error: %s", e)

    # 4. FinBERT loads lazily on first use (disabled warmup due to 1GB RAM limit)
    # try:
    #     import threading
    #     from app.ml.sentiment import load_finbert
    #     threading.Thread(target=load_finbert, daemon=True).start()
    #     logger.info("FinBERT warmup started in background ✅")
    # except Exception as e:
    #     logger.warning("FinBERT warmup error: %s", e)

    # 5. Start APScheduler
    setup_scheduler()
    logger.info("Scheduler started ✅")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("StockPred shutting down...")
    get_ticker().stop()
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="StockPred API",
    description="Volume + Momentum + News Signal Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten to your Vercel URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/health")
async def health():
    """Railway health check endpoint."""
    from app.services.kite_ticker import get_ticker
    ticker = get_ticker()
    kite_connected = ticker.kws.is_connected() if ticker.kws else False
    return {
        "status": "ok",
        "version": "1.0.0",
        "kite_connected": kite_connected,
    }
