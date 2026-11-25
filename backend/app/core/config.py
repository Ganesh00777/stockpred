from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str
    SYNC_DATABASE_URL: str

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Zerodha Kite
    KITE_API_KEY: Optional[str] = None
    KITE_API_SECRET: Optional[str] = None
    KITE_ACCESS_TOKEN: Optional[str] = None
    KITE_USER_ID: Optional[str] = None       # Zerodha user ID (e.g. AB1234)
    KITE_PASSWORD: Optional[str] = None      # Zerodha login password
    KITE_TOTP_SECRET: Optional[str] = None   # TOTP secret for 2FA auto-login

    TWELVE_DATA_API_KEY: str = ""

    # News
    NEWS_API_KEY: Optional[str] = None

    # Reddit
    REDDIT_CLIENT_ID: Optional[str] = None
    REDDIT_CLIENT_SECRET: Optional[str] = None
    REDDIT_USER_AGENT: str = "StockPredApp/1.0"

    # Alpha Vantage
    ALPHA_VANTAGE_KEY: Optional[str] = None

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # Resend
    RESEND_API_KEY: Optional[str] = None
    EMAIL_FROM: str = "alerts@yourdomain.com"
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""


    # App
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
