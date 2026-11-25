# StockPred — AI-Powered Stock Prediction App

NSE/BSE + US market signal engine with FinBERT news scoring, backtesting, and a React Native mobile app.

---

## Architecture

```
stockpred/
├── backend/        FastAPI + APScheduler + SQLAlchemy (async)
├── mobile/         React Native (Expo SDK 51) + Expo Router
└── frontend/       Web (Expo Web / Vercel)
```

**Stack**
- Backend: FastAPI, SQLAlchemy async, asyncpg, APScheduler
- Database: Supabase PostgreSQL 17 (hosted)
- Cache: Redis (Railway plugin)
- ML: FinBERT (ProsusAI/finbert) for news sentiment
- Data: Zerodha Kite Connect (primary) + yfinance (fallback)
- Deploy: Railway (backend), Vercel (web), Expo Go / EAS (mobile)

---

## Signal Engine

```
score = volume_score × 0.40 + momentum_score × 0.40 + news_score × 0.20
```

BUY signal if score > 0.6, SELL if score < 0.4, else HOLD.

---

## Environment Variables

Create `backend/.env`:

```env
# Database (URL-encode special chars: @ → %40, $ → %24)
DATABASE_URL=postgresql+asyncpg://postgres:<password>@db.<project>.supabase.co:5432/postgres
SYNC_DATABASE_URL=postgresql://postgres:<password>@db.<project>.supabase.co:5432/postgres

# Redis (Railway injects this automatically)
REDIS_URL=${{Redis.REDIS_URL}}

# Auth
SECRET_KEY=your-secret-key-min-32-chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# News
NEWS_API_KEY=your-newsapi-org-key

# Zerodha Kite (optional — yfinance used as fallback if not set)
KITE_API_KEY=
KITE_API_SECRET=
KITE_USER_ID=
KITE_PASSWORD=
KITE_TOTP_SECRET=

# Email (optional)
RESEND_API_KEY=
```

> **Important:** If your DB password contains `@` or `$`, URL-encode them:
> `Elevators@19993$` → `Elevators%4019993%24`

---

## Local Development (Mac M1/ARM)

### Prerequisites
- Python 3.11
- Node.js 18+
- Expo CLI

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env (see Environment Variables above)

# Run DB migrations
python scripts/migrate.py

# Seed initial OHLCV data
python scripts/seed_ohlcv.py

# Start dev server
uvicorn app.main:app --reload --port 8000
```

API docs: http://localhost:8000/docs

### Mobile

```bash
cd mobile
npm install
npx expo start
```

Scan the QR code with Expo Go app on your phone.

---

## Deployment

### Backend → Railway

1. Create a new project on [railway.app](https://railway.app)
2. Add a **Redis** plugin to the project
3. Connect your GitHub repo
4. In Service Settings → **Root Directory**: set to `backend`
5. Add environment variables (Settings → Variables):

```
DATABASE_URL=postgresql+asyncpg://postgres:<encoded-password>@db.<project>.supabase.co:5432/postgres
SYNC_DATABASE_URL=postgresql://postgres:<encoded-password>@db.<project>.supabase.co:5432/postgres
REDIS_URL=${{Redis.REDIS_URL}}
SECRET_KEY=<your-secret>
NEWS_API_KEY=<your-key>
```

6. Deploy — build takes ~3 minutes
7. In Settings → Networking → expose port `8000` to get a public URL

**Run migrations on Railway (first deploy only):**

```bash
npm install -g @railway/cli
railway login
cd backend
railway link   # select your project
railway run python scripts/migrate.py
railway run python scripts/seed_ohlcv.py
```

### Mobile API URL

Edit `mobile/api/client.ts`:

```typescript
export const API_BASE = __DEV__
  ? 'http://localhost:8000'
  : 'https://your-service.up.railway.app';  // ← your Railway URL
```

### Web → Vercel

```bash
cd mobile
npx expo export -p web
# Deploy the dist/ folder to Vercel
npx vercel dist/
```

---

## Scheduled Jobs (IST timezone)

| Job | Time | Description |
|-----|------|-------------|
| Kite daily login | 08:00 | Auto-login with TOTP |
| Fetch EOD OHLCV | 16:30 | Download day candles for all symbols |
| Fetch & score news | 16:45 | NewsAPI + RSS → FinBERT sentiment |
| Generate signals | 17:00 | Compute BUY/SELL/HOLD signals |
| Backtest evaluate | 17:30 | Score signals from 5–8 days ago |

---

## Database Schema

| Table | Description |
|-------|-------------|
| `users` | Auth — email, hashed password |
| `candles` | OHLCV data (ts, symbol, exchange, interval) |
| `signals` | BUY/SELL/HOLD with scores and backtest results |
| `news_items` | Headlines with FinBERT sentiment scores |
| `alert_rules` | User price/signal alerts |
| `watchlist_items` | User watchlists |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Get JWT tokens |
| GET | `/signals/{symbol}` | Signal history |
| GET | `/backtest/{symbol}` | Backtest stats |
| GET | `/alerts` | List alert rules |
| POST | `/alerts` | Create alert |
| PATCH | `/alerts/{id}` | Toggle alert on/off |
| DELETE | `/alerts/{id}` | Delete alert |
| GET | `/health` | Health check |

Full interactive docs at `/docs` (Swagger UI).

---

## Common Issues

**Railway build fails (OOM)**
Remove the FinBERT pre-download line from Dockerfile — it uses too much memory at build time. The model downloads on first use instead.

**DB connection error — special chars in password**
URL-encode `@` as `%40` and `$` as `%24` in both `DATABASE_URL` and `SYNC_DATABASE_URL`.

**`ImportError: cannot import name 'NSE_WATCHLIST'`**
The watchlists are defined in `app/services/news_fetcher.py`. Ensure you have the latest version of that file.

**TimescaleDB warning**
Supabase PG17 doesn't support TimescaleDB. The app skips it gracefully and uses plain Postgres indexes instead — this is fine for under 1M rows.

**Port already in use**
```bash
lsof -ti:8000 | xargs kill -9
```

---

## Security Notes

- Never commit `.env` files (covered by `.gitignore`)
- Rotate any GitHub PAT tokens that were accidentally shared in chat
- `SECRET_KEY` should be at least 32 random characters
- Supabase DB password URL-encoding is required but keep the original password safe
