"""
Signal Engine — Volume + Momentum + News Sentiment
Weights: Volume 40%, Momentum 40%, News 20%
"""
import logging
from dataclasses import dataclass
from typing import List, Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class SignalResult:
    symbol: str
    exchange: str
    direction: int          # 1=buy, -1=sell, 0=hold
    confidence: float       # 0.0 → 1.0
    volume_score: float
    momentum_score: float
    news_score: float
    reasons: List[str]
    price: float
    volume_ratio: float


def compute_momentum_score(df: pd.DataFrame) -> tuple[float, List[str]]:
    """
    Score momentum from -1.0 to +1.0.
    Uses RSI, MACD, EMA crossovers, ADX, ROC.
    """
    if len(df) < 50:
        return 0.0, []

    close = df["close"]
    volume = df["volume"]
    reasons = []
    votes = []

    # --- RSI(14) ---
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    rsi_now = rsi.iloc[-1]

    if rsi_now < 35:
        votes.append(1.0)
        reasons.append(f"RSI oversold ({rsi_now:.1f})")
    elif rsi_now > 65:
        votes.append(-1.0)
        reasons.append(f"RSI overbought ({rsi_now:.1f})")
    elif 45 < rsi_now < 65:
        votes.append(0.5)
        reasons.append(f"RSI bullish range ({rsi_now:.1f})")
    else:
        votes.append(0.0)

    # --- MACD(12,26,9) ---
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal_line

    if hist.iloc[-1] > 0 and hist.iloc[-2] <= 0:
        votes.append(1.0)
        reasons.append("MACD bullish crossover")
    elif hist.iloc[-1] < 0 and hist.iloc[-2] >= 0:
        votes.append(-1.0)
        reasons.append("MACD bearish crossover")
    elif hist.iloc[-1] > 0:
        votes.append(0.5)
        reasons.append("MACD histogram positive")
    else:
        votes.append(-0.5)

    # --- EMA 20/50 crossover ---
    ema20 = close.ewm(span=20, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    if ema20.iloc[-1] > ema50.iloc[-1] and ema20.iloc[-2] <= ema50.iloc[-2]:
        votes.append(1.0)
        reasons.append("EMA20 crossed above EMA50 (golden cross)")
    elif ema20.iloc[-1] < ema50.iloc[-1] and ema20.iloc[-2] >= ema50.iloc[-2]:
        votes.append(-1.0)
        reasons.append("EMA20 crossed below EMA50 (death cross)")
    elif close.iloc[-1] > ema20.iloc[-1]:
        votes.append(0.5)
        reasons.append("Price above EMA20")
    else:
        votes.append(-0.3)

    # --- Rate of Change 10d ---
    roc = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10] * 100
    if roc > 5:
        votes.append(0.8)
        reasons.append(f"Strong 10d momentum +{roc:.1f}%")
    elif roc < -5:
        votes.append(-0.8)
        reasons.append(f"Weak 10d momentum {roc:.1f}%")
    else:
        votes.append(roc / 10)

    # --- ADX (trend strength) ---
    high = df["high"]
    low = df["low"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    plus_dm = (high.diff()).clip(lower=0)
    minus_dm = (-low.diff()).clip(lower=0)
    plus_di = 100 * plus_dm.rolling(14).mean() / atr
    minus_di = 100 * minus_dm.rolling(14).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(14).mean().iloc[-1]

    if adx > 25:
        # Strong trend — amplify existing direction
        multiplier = min(1.3, 1 + (adx - 25) / 100)
        votes = [v * multiplier for v in votes]
        reasons.append(f"Strong trend (ADX {adx:.0f})")

    score = float(np.clip(np.mean(votes), -1.0, 1.0))
    return score, reasons


def compute_volume_score(df: pd.DataFrame) -> tuple[float, List[str]]:
    """
    Score volume from -1.0 to +1.0.
    Key signal: volume surge + price direction alignment.
    """
    if len(df) < 21:
        return 0.0, []

    volume = df["volume"]
    close = df["close"]
    reasons = []

    avg_vol_20d = volume.iloc[-21:-1].mean()
    today_vol = volume.iloc[-1]
    vol_ratio = today_vol / avg_vol_20d if avg_vol_20d > 0 else 1.0

    today_return = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]

    score = 0.0

    # Volume surge
    if vol_ratio >= 3.0:
        base = 0.9
        reasons.append(f"Extreme volume surge {vol_ratio:.1f}x avg")
    elif vol_ratio >= 2.0:
        base = 0.7
        reasons.append(f"High volume surge {vol_ratio:.1f}x avg")
    elif vol_ratio >= 1.5:
        base = 0.4
        reasons.append(f"Above-avg volume {vol_ratio:.1f}x")
    elif vol_ratio < 0.7:
        base = -0.3
        reasons.append(f"Low volume ({vol_ratio:.1f}x avg) — weak move")
    else:
        base = 0.0

    # Align with price direction
    if today_return > 0:
        score = base
    elif today_return < 0:
        score = -base
        if vol_ratio >= 2.0:
            reasons.append("High-volume sell-off — caution")
    else:
        score = base * 0.3

    # OBV trend (5-day)
    obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
    obv_5d_change = (obv.iloc[-1] - obv.iloc[-6]) / (abs(obv.iloc[-6]) + 1)
    if obv_5d_change > 0.05:
        score = min(1.0, score + 0.2)
        reasons.append("OBV rising (accumulation)")
    elif obv_5d_change < -0.05:
        score = max(-1.0, score - 0.2)
        reasons.append("OBV falling (distribution)")

    return float(np.clip(score, -1.0, 1.0)), reasons


def compute_news_score(news_items: List[dict], symbol: str) -> tuple[float, List[str]]:
    """
    Score news sentiment from -1.0 to +1.0.
    Weights recent items more heavily.
    """
    relevant = [n for n in news_items if symbol in n.get("symbols_mentioned", [])]
    if not relevant:
        return 0.0, []

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    weighted_scores = []
    reasons = []

    label_map = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}

    for item in relevant:
        label = item.get("finbert_label", "neutral")
        score = label_map.get(label, 0.0) * item.get("finbert_score", 0.5)

        # Recency weight: items from last 6h get 1.0, 48h get 0.2
        try:
            pub = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
            age_hours = (now - pub).total_seconds() / 3600
            weight = max(0.2, 1.0 - age_hours / 60)
        except Exception:
            weight = 0.5

        weighted_scores.append(score * weight)

    if not weighted_scores:
        return 0.0, []

    final = float(np.clip(np.mean(weighted_scores), -1.0, 1.0))
    positive = sum(1 for s in weighted_scores if s > 0)
    negative = sum(1 for s in weighted_scores if s < 0)

    if positive > negative:
        reasons.append(f"Positive news sentiment ({positive} of {len(relevant)} articles bullish)")
    elif negative > positive:
        reasons.append(f"Negative news sentiment ({negative} of {len(relevant)} articles bearish)")
    else:
        reasons.append(f"Mixed news ({len(relevant)} articles)")

    return final, reasons


def generate_signal(
    symbol: str,
    exchange: str,
    df: pd.DataFrame,
    news_items: List[dict],
) -> Optional[SignalResult]:
    """
    Generate a composite signal for one symbol.
    Weights: Volume 40%, Momentum 40%, News 20%
    """
    if df is None or len(df) < 50:
        return None

    df = df.sort_values("ts").reset_index(drop=True)
    price = float(df["close"].iloc[-1])
    vol_ratio = float(df["volume"].iloc[-1] / df["volume"].iloc[-21:-1].mean())

    vol_score, vol_reasons = compute_volume_score(df)
    mom_score, mom_reasons = compute_momentum_score(df)
    news_score, news_reasons = compute_news_score(news_items, symbol)

    # Composite score
    composite = (vol_score * 0.40) + (mom_score * 0.40) + (news_score * 0.20)

    # Direction threshold
    if composite >= 0.25:
        direction = 1
    elif composite <= -0.25:
        direction = -1
    else:
        direction = 0

    # Confidence = how far from neutral, scaled to 0–1
    confidence = min(1.0, abs(composite) / 0.8)

    # Only fire if volume + momentum agree (no weak single-factor signals)
    if direction != 0:
        vol_dir = 1 if vol_score > 0 else -1 if vol_score < 0 else 0
        mom_dir = 1 if mom_score > 0 else -1 if mom_score < 0 else 0
        if vol_dir != 0 and mom_dir != 0 and vol_dir != mom_dir:
            # Volume and momentum conflict — downgrade to hold
            direction = 0
            confidence = confidence * 0.3

    all_reasons = vol_reasons + mom_reasons + news_reasons

    return SignalResult(
        symbol=symbol,
        exchange=exchange,
        direction=direction,
        confidence=round(confidence, 3),
        volume_score=round(vol_score, 3),
        momentum_score=round(mom_score, 3),
        news_score=round(news_score, 3),
        reasons=all_reasons,
        price=price,
        volume_ratio=round(vol_ratio, 2),
    )
