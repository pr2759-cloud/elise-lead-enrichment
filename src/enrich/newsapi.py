"""NewsAPI enrichment: recent news mentions, trigger events, technology signals."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from ..config import NEWSAPI_ENDPOINT, NEWSAPI_KEY
from ..http_client import HTTPError, get_json
from ..models import NewsEnrichment
from ..cache import get_cache

log = logging.getLogger(__name__)


HIGH_SIGNAL_TRIGGERS = [
    "raised", "series a", "series b", "series c", "funding", "funds",
    "acquired", "acquires", "acquisition",
    "launched", "launches", "debuts",
    "opens", "opened", "opening",
    "expands", "expanding", "expansion",
    "appointed", "appoints", "hires", "named",
    "partnership", "partners with",
    "announces", "announced",
    "breaks ground", "breaking ground",
]

TECH_SIGNAL_KEYWORDS = [
    "technology", "tech", "digital", "ai", "artificial intelligence",
    "proptech", "prop tech", "software", "platform", "automation",
    "chatbot", "machine learning",
]


def _search_news(query: str, since_days: int) -> List[dict]:
    """Call NewsAPI /v2/everything. Returns [] on any failure."""
    if not NEWSAPI_KEY:
        return []
    params = {
        "q": f'"{query}"',  # exact phrase match
        "from": (datetime.utcnow() - timedelta(days=since_days)).strftime("%Y-%m-%d"),
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 20,
        "apiKey": NEWSAPI_KEY,
    }
    try:
        data = get_json(NEWSAPI_ENDPOINT, params=params)
        return data.get("articles", []) if data else []
    except HTTPError as e:
        log.warning("NewsAPI call failed for %s: %s", query, e)
        return []


def _first_match(articles: List[dict], keywords: List[str]) -> Optional[dict]:
    for a in articles:
        hay = ((a.get("title") or "") + " " + (a.get("description") or "")).lower()
        if any(k in hay for k in keywords):
            return a
    return None


def enrich_news(company: str) -> NewsEnrichment:
    """Return best-effort news enrichment for the company.

    NewsAPI's free Developer tier only allows a 30-day lookback window, so we
    request 29 days (safety margin) and use it for both the 30d and 90d buckets.
    On a paid tier this could be extended to 90d for a richer velocity signal.
    """
    company = (company or "").strip()
    if not company:
        return NewsEnrichment(error="empty company name")

    if not NEWSAPI_KEY:
        return NewsEnrichment(error="no NEWSAPI_KEY configured")

    cache = get_cache()
    cached = cache.get("newsapi", company.lower())
    if cached is not None:
        try:
            return NewsEnrichment(**cached)
        except TypeError:
            pass

    # Free tier allows a maximum ~30-day lookback. Using 29 to be safely under.
    articles_all = _search_news(company, since_days=29)
    result = NewsEnrichment()

    cutoff_30d = datetime.utcnow() - timedelta(days=30)
    articles_30d = []
    for a in articles_all:
        pub = a.get("publishedAt", "")
        try:
            d = datetime.strptime(pub[:10], "%Y-%m-%d")
            if d >= cutoff_30d:
                articles_30d.append(a)
        except ValueError:
            continue

    result.articles_30d = len(articles_30d)
    # On the free tier we can't see past 30 days, so 90d count == 30d count.
    # This makes the news_velocity signal slightly less discriminating but keeps
    # the pipeline working without errors.
    result.articles_90d = len(articles_all)

    trigger_30 = _first_match(articles_30d, HIGH_SIGNAL_TRIGGERS)
    if trigger_30:
        result.trigger_headline_30d = trigger_30.get("title")
        result.trigger_url = trigger_30.get("url")

    trigger_90 = _first_match(articles_all, HIGH_SIGNAL_TRIGGERS)
    if trigger_90:
        result.trigger_headline_90d = trigger_90.get("title")
        if not result.trigger_url:
            result.trigger_url = trigger_90.get("url")

    tech_match = _first_match(articles_all, TECH_SIGNAL_KEYWORDS)
    result.has_tech_news = tech_match is not None

    if articles_all:
        top = articles_all[0]
        result.top_headline = top.get("title")
        result.top_url = top.get("url")

    cache.set("newsapi", company.lower(), result.__dict__)
    return result
