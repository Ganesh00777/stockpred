"""
All API routes — signals, candles, news, alerts, auth, WebSocket.
"""
import json
import asyncio
import logging
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import (
    get_current_user, verify_password, hash_password,
    create_access_token, create_refresh_token
)
from app.db.database import get_db
from app.db.models import User, AlertRule, Signal, Candle, NewsItem, WatchlistItem
from app.services.data_fetcher import fetch_ohlcv, fetch_volume_surge_candidates
from app.services.news_fetcher import fetch_all_news, NSE_WATCHLIST, US_WATCHLIST
from app.ml.sentiment import score_headlines
from app.ml.signal_engine import generate_signal
from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

ws_manager = ConnectionManager()

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RegisterRequest(BaseModel):
    email: str
    password: str

class AlertRuleCreate(BaseModel):
    symbol: str
    exchange: str
    direction: Optional[int] = None   # None=any, 1=buy, -1=sell
    min_confidence: float = 0.6
    channel: str = "telegram"         # telegram | email | both

class AlertRuleToggle(BaseModel):
    is_active: bool

class SignalResponse(BaseModel):
    symbol: str
    exchange: str
    direction: int
    confidence: float
    volume_score: float
    momentum_score: float
    news_score: float
    reasons: List[str]
    price: float
    volume_ratio: float
    generated_at: str

# ── Auth ──────────────────────────────────────────────────────────────────────

@router.post("/auth/register", tags=["Auth"])
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check email not taken
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=req.email, hashed_password=hash_password(req.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {
        "access_token": create_access_token(str(user.id)),
        "refresh_token": create_refresh_token(str(user.id)),
        "token_type": "bearer",
    }


@router.post("/auth/login", response_model=TokenResponse, tags=["Auth"])
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )

# ── Signals ───────────────────────────────────────────────────────────────────

@router.get("/signals", tags=["Signals"])
async def get_signals(
    symbols: Optional[str] = Query(None, description="Comma-separated symbols"),
    exchange: str = Query("NSE"),
    min_confidence: float = Query(0.4),
    limit: int = Query(20),
    user_id: str = Depends(get_current_user),
):
    """Get latest signals for given symbols or full watchlist."""
    target_symbols = symbols.split(",") if symbols else NSE_WATCHLIST[:20]

    # Fetch news once for all
    all_symbols = NSE_WATCHLIST + US_WATCHLIST
    articles = fetch_all_news(all_symbols)
    scored_articles = score_headlines(articles)

    results = []
    for symbol in target_symbols[:limit]:
        df = fetch_ohlcv(symbol.strip(), exchange, period="6mo")
        signal = generate_signal(symbol.strip(), exchange, df, scored_articles)
        if signal and signal.confidence >= min_confidence:
            results.append({
                "symbol": signal.symbol,
                "exchange": signal.exchange,
                "direction": signal.direction,
                "confidence": signal.confidence,
                "volume_score": signal.volume_score,
                "momentum_score": signal.momentum_score,
                "news_score": signal.news_score,
                "reasons": signal.reasons,
                "price": signal.price,
                "volume_ratio": signal.volume_ratio,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            })

    results.sort(key=lambda x: x["confidence"], reverse=True)
    return {"signals": results, "count": len(results)}


@router.get("/signals/breakouts", tags=["Signals"])
async def get_volume_breakouts(
    min_ratio: float = Query(2.0),
    user_id: str = Depends(get_current_user),
):
    """Stocks with volume surge >= min_ratio * 20d avg — primary breakout screen."""
    candidates = fetch_volume_surge_candidates(min_ratio=min_ratio)
    return {"breakouts": candidates, "count": len(candidates)}


@router.get("/signals/{symbol}/history", tags=["Signals"])
async def get_signal_history(
    symbol: str,
    exchange: str = Query("NSE"),
    days: int = Query(30),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Signal history with actual returns for backtest view."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(Signal)
        .where(Signal.symbol == symbol.upper())
        .where(Signal.exchange == exchange.upper())
        .where(Signal.generated_at >= since)
        .order_by(Signal.generated_at.desc())
        .limit(100)
    )
    signals = result.scalars().all()
    return {
        "symbol": symbol,
        "history": [
            {
                "id": str(s.id),
                "direction": s.direction,
                "confidence": s.confidence,
                "price_at_signal": s.price_at_signal,
                "actual_return_5d": s.actual_return_5d,
                "backtest_correct": s.backtest_correct,
                "generated_at": s.generated_at.isoformat() if s.generated_at else None,
                "reasons": s.signal_reasons or [],
            }
            for s in signals
        ],
    }

# ── Candles ───────────────────────────────────────────────────────────────────

@router.get("/candles/{symbol}", tags=["Candles"])
async def get_candles(
    symbol: str,
    exchange: str = Query("NSE"),
    interval: str = Query("1d"),
    period: str = Query("6mo"),
    user_id: str = Depends(get_current_user),
):
    """OHLCV data for charting."""
    df = fetch_ohlcv(symbol, exchange, period=period, interval=interval)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")

    records = df[["ts", "open", "high", "low", "close", "volume"]].copy()
    records["ts"] = records["ts"].astype(str)
    return {
        "symbol": symbol,
        "exchange": exchange,
        "interval": interval,
        "candles": records.to_dict(orient="records"),
    }

# ── News ──────────────────────────────────────────────────────────────────────

@router.get("/news", tags=["News"])
async def get_news(
    symbols: Optional[str] = Query(None),
    hours: int = Query(48),
    user_id: str = Depends(get_current_user),
):
    """Scored news items for given symbols."""
    target = symbols.split(",") if symbols else NSE_WATCHLIST[:10]
    articles = fetch_all_news(target)
    scored = score_headlines(articles)

    # Filter to relevant symbols
    relevant = [
        a for a in scored
        if any(s in a.get("symbols_mentioned", []) for s in target)
    ]
    return {"news": relevant[:50], "count": len(relevant)}

# ── Backtest ──────────────────────────────────────────────────────────────────

@router.get("/backtest/{symbol}", tags=["Backtest"])
async def get_backtest(
    symbol: str,
    exchange: str = Query("NSE"),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Signal accuracy, win rate, avg return for a symbol."""
    result = await db.execute(
        select(Signal)
        .where(Signal.symbol == symbol.upper())
        .where(Signal.exchange == exchange.upper())
        .where(Signal.backtest_correct != None)  # noqa: E711
        .order_by(Signal.generated_at.desc())
        .limit(200)
    )
    signals = result.scalars().all()

    if not signals:
        return {
            "symbol": symbol,
            "total_signals": 0,
            "win_rate": None,
            "avg_return_5d": None,
            "signals": [],
        }

    correct = [s for s in signals if s.backtest_correct]
    win_rate = len(correct) / len(signals) if signals else 0
    returns = [s.actual_return_5d for s in signals if s.actual_return_5d is not None]
    avg_return = sum(returns) / len(returns) if returns else None

    return {
        "symbol": symbol,
        "total_signals": len(signals),
        "win_rate": round(win_rate, 3),
        "avg_return_5d": round(avg_return, 4) if avg_return else None,
        "signals": [
            {
                "direction": s.direction,
                "confidence": s.confidence,
                "price_at_signal": s.price_at_signal,
                "actual_return_5d": s.actual_return_5d,
                "backtest_correct": s.backtest_correct,
                "generated_at": s.generated_at.isoformat() if s.generated_at else None,
            }
            for s in signals[:50]
        ],
    }

# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts", tags=["Alerts"])
async def list_alerts(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """List user's alert rules."""
    result = await db.execute(
        select(AlertRule)
        .where(AlertRule.user_id == user_id)
        .order_by(AlertRule.created_at.desc())
    )
    alerts = result.scalars().all()
    return {
        "alerts": [
            {
                "id": str(a.id),
                "symbol": a.symbol,
                "exchange": a.exchange,
                "direction": a.direction,
                "min_confidence": a.min_confidence,
                "channel": a.channel,
                "is_active": a.is_active,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in alerts
        ]
    }


@router.post("/alerts", tags=["Alerts"])
async def create_alert(
    rule: AlertRuleCreate,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Create an alert rule."""
    alert = AlertRule(
        user_id=user_id,
        symbol=rule.symbol.upper(),
        exchange=rule.exchange.upper(),
        direction=rule.direction,
        min_confidence=rule.min_confidence,
        channel=rule.channel,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return {"status": "created", "id": str(alert.id)}


@router.patch("/alerts/{alert_id}", tags=["Alerts"])
async def toggle_alert(
    alert_id: str,
    body: AlertRuleToggle,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Enable/disable an alert rule."""
    result = await db.execute(
        select(AlertRule)
        .where(AlertRule.id == alert_id)
        .where(AlertRule.user_id == user_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_active = body.is_active
    await db.commit()
    return {"status": "updated", "is_active": alert.is_active}


@router.delete("/alerts/{alert_id}", tags=["Alerts"])
async def delete_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
):
    """Delete an alert rule."""
    result = await db.execute(
        select(AlertRule)
        .where(AlertRule.id == alert_id)
        .where(AlertRule.user_id == user_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    await db.delete(alert)
    await db.commit()
    return {"status": "deleted"}

# ── WebSocket ─────────────────────────────────────────────────────────────────

@router.websocket("/ws/signals")
async def websocket_signals(ws: WebSocket):
    """Real-time signal feed during market hours."""
    await ws_manager.connect(ws)
    try:
        while True:
            # Keep-alive ping every 30s
            await asyncio.sleep(30)
            await ws.send_json({"type": "ping", "ts": datetime.now(timezone.utc).isoformat()})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
