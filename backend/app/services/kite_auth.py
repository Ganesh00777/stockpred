"""
Kite daily auto-login using TOTP.
Run this script every morning before market open (scheduled at 08:00 IST).
Writes fresh KITE_ACCESS_TOKEN to Redis so the app picks it up.

Usage:
    python -m app.services.kite_auth

Or set KITE_TOTP_SECRET in .env and the scheduler calls it automatically.
"""
import logging
import os
import sys
import redis
import httpx
import pyotp
import hashlib

from app.core.config import settings

logger = logging.getLogger(__name__)


def generate_totp(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def login_and_get_token() -> str | None:
    """
    Full Kite login flow:
    1. POST /session/token with api_key + request_token + checksum
    But first we need a request_token via browser login OR TOTP automation.

    For server-side automation, we use the Kite login API directly with TOTP.
    """
    if not settings.KITE_API_KEY:
        logger.error("KITE_API_KEY not set")
        return None

    if not settings.KITE_TOTP_SECRET:
        logger.warning(
            "KITE_TOTP_SECRET not set — cannot auto-login.\n"
            "Set KITE_TOTP_SECRET in .env to enable daily auto-login.\n"
            "Get it: Zerodha → My Profile → Enable 2FA → reveal TOTP secret"
        )
        return None

    try:
        client = httpx.Client(timeout=15, follow_redirects=True)

        # Step 1: Get login page (sets session cookie)
        resp = client.get("https://kite.zerodha.com/api/login")

        # Step 2: POST credentials
        totp_code = generate_totp(settings.KITE_TOTP_SECRET)
        resp = client.post("https://kite.zerodha.com/api/login", data={
            "user_id": settings.KITE_USER_ID,
            "password": settings.KITE_PASSWORD,
        })
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            logger.error("Kite login step 1 failed: %s", data)
            return None

        request_id = data["data"]["request_id"]

        # Step 3: Submit TOTP
        resp = client.post("https://kite.zerodha.com/api/twofa", data={
            "user_id": settings.KITE_USER_ID,
            "request_id": request_id,
            "twofa_value": totp_code,
            "twofa_type": "totp",
        })
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "success":
            logger.error("Kite TOTP failed: %s", data)
            return None

        request_token = data["data"]["request_token"]

        # Step 4: Exchange request_token for access_token
        checksum = hashlib.sha256(
            f"{settings.KITE_API_KEY}{request_token}{settings.KITE_API_SECRET}".encode()
        ).hexdigest()

        resp = client.post("https://api.kite.trade/session/token", data={
            "api_key": settings.KITE_API_KEY,
            "request_token": request_token,
            "checksum": checksum,
        }, headers={"X-Kite-Version": "3"})
        resp.raise_for_status()
        session_data = resp.json()["data"]

        access_token = session_data["access_token"]
        logger.info("Kite login successful — access_token obtained")

        # Step 5: Store in Redis (expires 24h)
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.setex("kite:access_token", 86400, access_token)

        # Also update env for current process
        os.environ["KITE_ACCESS_TOKEN"] = access_token
        settings.KITE_ACCESS_TOKEN = access_token

        return access_token

    except Exception as e:
        logger.error("Kite auto-login failed: %s", e)
        return None


def get_or_refresh_token() -> str | None:
    """Get token from Redis (fast) or login fresh."""
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        token = r.get("kite:access_token")
        if token:
            settings.KITE_ACCESS_TOKEN = token
            return token
    except Exception:
        pass

    # Token missing or Redis down — try fresh login
    return login_and_get_token()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    token = login_and_get_token()
    if token:
        print(f"✅ Login successful. Token: {token[:20]}...")
    else:
        print("❌ Login failed. Check logs above.")
        sys.exit(1)
