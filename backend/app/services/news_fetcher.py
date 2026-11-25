"""
News ingestion from NewsAPI + RSS feeds.
Symbols are extracted by simple keyword matching.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict
import feedparser
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms"),
    ("Moneycontrol", "https://www.moneycontrol.com/rss/marketoutlook.xml"),
    ("Business Standard", "https://www.business-standard.com/rss/markets-106.rss"),
    ("LiveMint Markets", "https://www.livemint.com/rss/markets"),
]

# NSE watchlist — top Nifty 50 + popular mid-caps
NSE_WATCHLIST = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "HINDUNILVR",
    "BHARTIARTL", "ITC", "KOTAKBANK", "LT", "SBIN", "AXISBANK", "BAJFINANCE",
    "ASIANPAINT", "MARUTI", "TITAN", "SUNPHARMA", "WIPRO", "ULTRACEMCO",
    "NESTLEIND", "POWERGRID", "NTPC", "ONGC", "COALINDIA", "JSWSTEEL",
    "TATAMOTORS", "TATASTEEL", "ADANIPORTS", "ADANIENT", "HCLTECH",
    "TECHM", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP", "BAJAJFINSV",
    "BPCL", "EICHERMOT", "GRASIM", "HEROMOTOCO", "INDUSINDBK", "M&M",
    "SBILIFE", "SHREECEM", "TATACONSUM", "VEDL", "BRITANNIA", "LTIM", "HDFCLIFE",
]

# US watchlist — S&P 500 tech + popular large-caps
US_WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AVGO",
    "JPM", "V", "UNH", "MA", "JNJ", "HD", "PG", "MRK", "ABBV", "LLY",
    "BAC", "CVX", "KO", "PEP", "TMO", "COST", "WMT", "MCD", "CSCO",
    "ACN", "ABT", "DHR", "NKE", "ADBE", "CRM", "TXN", "ORCL", "QCOM",
    "AMD", "INTC", "NFLX", "PYPL", "UBER", "SHOP", "SQ", "COIN", "PLTR",
]


def fetch_newsapi(query: str = "Indian stock market NSE BSE", hours_back: int = 48) -> List[Dict]:
    """Fetch headlines from NewsAPI."""
    if not settings.NEWS_API_KEY:
        logger.warning("NEWS_API_KEY not set, skipping NewsAPI")
        return []

    from_date = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = "https://newsapi.org/v2/everything"
    params = {
        "q": query,
        "from": from_date,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": 100,
        "apiKey": settings.NEWS_API_KEY,
    }

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        articles = []
        for a in data.get("articles", []):
            articles.append({
                "headline": a.get("title", ""),
                "url": a.get("url", ""),
                "source": a.get("source", {}).get("name", ""),
                "published_at": a.get("publishedAt", ""),
            })
        return articles

    except Exception as e:
        logger.error(f"NewsAPI error: {e}")
        return []


def fetch_rss_feeds() -> List[Dict]:
    """Fetch headlines from RSS feeds."""
    articles = []
    for name, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:20]:
                articles.append({
                    "headline": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "source": name,
                    "published_at": entry.get("published", ""),
                })
        except Exception as e:
            logger.error(f"RSS error {name}: {e}")

    return articles


def extract_symbols_from_headline(headline: str, symbol_list: List[str]) -> List[str]:
    """
    Simple keyword match — returns symbols mentioned in a headline.
    For production, replace with a fine-tuned NER model.
    """
    headline_upper = headline.upper()
    found = []
    for symbol in symbol_list:
        if symbol.upper() in headline_upper:
            found.append(symbol)
    return found


def fetch_all_news(symbol_list: List[str]) -> List[Dict]:
    """Fetch and merge news from all sources."""
    newsapi = fetch_newsapi()
    rss = fetch_rss_feeds()
    all_articles = newsapi + rss

    # Deduplicate by headline
    seen = set()
    unique = []
    for a in all_articles:
        key = a["headline"][:80]
        if key not in seen:
            seen.add(key)
            a["symbols_mentioned"] = extract_symbols_from_headline(
                a["headline"], symbol_list
            )
            unique.append(a)

    logger.info(f"Fetched {len(unique)} unique news items")
    return unique