"""
Zerodha Kite WebSocket ticker — real-time NSE price feed.
Runs as a background thread, pushes ticks to Redis.
Falls back gracefully if Kite creds are missing.
"""
import json
import logging
import threading
import time
from typing import Dict, List, Optional
import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# NSE instrument tokens — Nifty 50 key stocks
# Get full list: kite.instruments('NSE') → filter by tradingsymbol
INSTRUMENT_TOKENS: Dict[str, int] = {
    "RELIANCE":    738561,
    "TCS":         2953217,
    "HDFCBANK":    341249,
    "INFY":        408065,
    "ICICIBANK":   1270529,
    "HINDUNILVR":  356865,
    "ITC":         424961,
    "SBIN":        779521,
    "BHARTIARTL":  2714625,
    "KOTAKBANK":   492033,
    "LT":          2939649,
    "AXISBANK":    1510401,
    "ASIANPAINT":  60417,
    "MARUTI":      2815745,
    "TITAN":       897537,
    "SUNPHARMA":   857857,
    "WIPRO":       969473,
    "BAJFINANCE":  225537,
    "NESTLEIND":   4598529,
    "TATASTEEL":   895745,
    "HCLTECH":     1850625,
    "TECHM":       3465729,
    "NTPC":        2977281,
    "POWERGRID":   3834113,
    "DIVISLAB":    2800641,
}

# Reverse map: token → symbol
TOKEN_TO_SYMBOL = {v: k for k, v in INSTRUMENT_TOKENS.items()}

_ticker_instance = None
_ticker_lock = threading.Lock()


class KiteTicker:
    """Wraps kiteconnect.KiteTicker with Redis push and auto-reconnect."""

    def __init__(self):
        self.kws = None
        self.redis_client: Optional[redis.Redis] = None
        self.running = False
        self._thread: Optional[threading.Thread] = None

    def _get_redis(self) -> redis.Redis:
        if self.redis_client is None:
            self.redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        return self.redis_client

    def _push_tick(self, symbol: str, tick: dict):
        """Push latest tick to Redis with 10m TTL."""
        r = self._get_redis()
        key = f"tick:{symbol}"
        r.setex(key, 600, json.dumps(tick))
        # Publish to channel for WebSocket consumers
        r.publish(f"ticks", json.dumps({"symbol": symbol, **tick}))

    def start(self):
        if not settings.KITE_API_KEY or not settings.KITE_ACCESS_TOKEN:
            logger.warning("Kite creds missing — ticker not started, using yfinance fallback")
            return

        with _ticker_lock:
            if self.running:
                return
            self.running = True

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("KiteTicker started")

    def _run(self):
        try:
            from kiteconnect import KiteTicker as KT
        except ImportError:
            logger.error("kiteconnect not installed — pip install kiteconnect")
            return

        tokens = list(INSTRUMENT_TOKENS.values())

        while self.running:
            try:
                self.kws = KT(settings.KITE_API_KEY, settings.KITE_ACCESS_TOKEN)

                def on_ticks(ws, ticks):
                    for tick in ticks:
                        token = tick.get("instrument_token")
                        symbol = TOKEN_TO_SYMBOL.get(token)
                        if not symbol:
                            continue
                        payload = {
                            "ltp":        tick.get("last_price"),
                            "open":       tick.get("ohlc", {}).get("open"),
                            "high":       tick.get("ohlc", {}).get("high"),
                            "low":        tick.get("ohlc", {}).get("low"),
                            "close":      tick.get("ohlc", {}).get("close"),
                            "volume":     tick.get("volume_traded"),
                            "change_pct": tick.get("change"),
                            "timestamp":  str(tick.get("timestamp", "")),
                        }
                        self._push_tick(symbol, payload)

                def on_connect(ws, response):
                    logger.info("Kite WS connected — subscribing to %d tokens", len(tokens))
                    ws.subscribe(tokens)
                    ws.set_mode(ws.MODE_QUOTE, tokens)

                def on_close(ws, code, reason):
                    logger.warning("Kite WS closed: %s %s", code, reason)

                def on_error(ws, code, reason):
                    logger.error("Kite WS error: %s %s", code, reason)

                self.kws.on_ticks = on_ticks
                self.kws.on_connect = on_connect
                self.kws.on_close = on_close
                self.kws.on_error = on_error

                self.kws.connect(threaded=True)

                # Keep thread alive; reconnect on drop
                while self.running and self.kws.is_connected():
                    time.sleep(5)

                logger.warning("Kite WS disconnected — reconnecting in 10s")
                time.sleep(10)

            except Exception as e:
                logger.error("KiteTicker error: %s — retrying in 15s", e)
                time.sleep(15)

    def stop(self):
        self.running = False
        if self.kws:
            try:
                self.kws.close()
            except Exception:
                pass

    def get_latest_tick(self, symbol: str) -> Optional[dict]:
        """Get latest cached tick from Redis."""
        try:
            r = self._get_redis()
            raw = r.get(f"tick:{symbol}")
            return json.loads(raw) if raw else None
        except Exception:
            return None


def get_ticker() -> KiteTicker:
    global _ticker_instance
    if _ticker_instance is None:
        _ticker_instance = KiteTicker()
    return _ticker_instance


def get_live_price(symbol: str) -> Optional[float]:
    """
    Get live price: Kite tick (if market open) → yfinance fallback.
    """
    tick = get_ticker().get_latest_tick(symbol)
    if tick and tick.get("ltp"):
        return float(tick["ltp"])

    # Fallback to yfinance
    try:
        import yfinance as yf
        ticker = f"{symbol}.NS" if not symbol.upper() in ["AAPL","MSFT","NVDA","GOOGL","META","AMZN","TSLA","AMD","NFLX","PLTR"] else symbol
        t = yf.Ticker(ticker)
        info = t.fast_info
        return float(info.last_price)
    except Exception:
        return None
