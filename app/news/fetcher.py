import feedparser
import httpx
import structlog
from datetime import datetime
from app.news.sentiment import classify_sentiment

logger = structlog.get_logger()

RSS_FEEDS = {
    "moneycontrol": "https://www.moneycontrol.com/rss/MCtopnews.xml",
    "et_markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "nse": "https://www.nseindia.com/api/rss",  # NSE circulars — may need auth
}

NIFTY_KEYWORDS = ["nifty", "sensex", "market", "index", "rbi", "repo rate", "inflation", "gdp", "budget"]
BANKNIFTY_KEYWORDS = ["bank nifty", "banking", "rbi", "rate", "credit", "nbfc", "hdfc", "sbi", "icici"]


def map_to_symbol(text: str) -> str | None:
    text_lower = text.lower()
    if any(kw in text_lower for kw in BANKNIFTY_KEYWORDS):
        return "BANKNIFTY"
    if any(kw in text_lower for kw in NIFTY_KEYWORDS):
        return "NIFTY"
    return None


async def fetch_news() -> list[dict]:
    articles = []
    for source, url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:  # Latest 10 per source
                title = entry.get("title", "")
                sentiment_label, score = classify_sentiment(title)
                symbol = map_to_symbol(title)
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    published = datetime(*entry.published_parsed[:6])

                articles.append({
                    "headline": title,
                    "source": source,
                    "sentiment": sentiment_label,
                    "score": score,
                    "symbol": symbol,
                    "url": entry.get("link"),
                    "published_at": published,
                })
        except Exception as e:
            logger.warning("Failed to fetch RSS feed", source=source, error=str(e))

    logger.info("News fetched", count=len(articles))
    return articles
