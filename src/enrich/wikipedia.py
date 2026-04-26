"""Wikipedia enrichment: company existence, industry cues, scale indicators."""
from __future__ import annotations
import logging
import re
from typing import Optional

import requests

from ..config import WIKIPEDIA_API, WIKIPEDIA_SUMMARY
from ..http_client import HTTPError, get_json
from ..models import CompanyEnrichment
from ..cache import get_cache

log = logging.getLogger(__name__)


# Keyword sets used for industry classification and scale detection.
MULTIFAMILY_KW = [
    "multifamily", "multi-family", "apartment", "apartments", "residential rental",
]
PROP_MGMT_KW = [
    "property management", "property manager", "property managers",
    "property-management",
]
RE_OWNER_KW = [
    "real estate", "real-estate", "reit", "real estate investment trust",
    "real estate company", "real estate owner", "owner-operator",
]
ADJACENT_KW = [
    "hospitality", "hotel", "hotels", "senior living", "student housing",
    "co-living", "coliving", "assisted living", "serviced apartments",
]

# Signals that the company manages many units/properties
SCALE_PATTERNS = [
    r"\b(\d{1,3}(?:,\d{3})+|\d{3,})\s+(?:units|apartments|residences|homes)\b",
    r"manages\s+(?:over\s+)?\d",
    r"portfolio\s+of\s+(?:over\s+)?\d",
    r"\b(\d{2,})\s+(?:properties|buildings|communities)\b",
]


def _has_any(text: str, needles) -> bool:
    t = text.lower()
    return any(n in t for n in needles)


def _has_scale_signal(text: str) -> bool:
    t = text.lower()
    for pat in SCALE_PATTERNS:
        if re.search(pat, t):
            return True
    return False


def _search(company: str) -> Optional[dict]:
    """Use MediaWiki search to find the most plausible page."""
    params = {
        "action": "query",
        "list": "search",
        "srsearch": company,
        "srlimit": 5,
        "format": "json",
    }
    try:
        return get_json(WIKIPEDIA_API, params=params)
    except HTTPError as e:
        log.warning("Wikipedia search failed for %s: %s", company, e)
        return None


def _summary(title: str) -> Optional[dict]:
    """Fetch the REST summary endpoint for a page title."""
    url = WIKIPEDIA_SUMMARY + requests.utils.quote(title, safe="")
    try:
        return get_json(url, accept_404=True)
    except HTTPError as e:
        log.warning("Wikipedia summary failed for %s: %s", title, e)
        return None


def enrich_company_wikipedia(company: str) -> CompanyEnrichment:
    """Return best-effort company enrichment from Wikipedia.

    - If a standalone page exists, we mark has_wikipedia_page=True.
    - If the company is only referenced within another page (parent), we mark
      parent_mention_only=True.
    - Keyword flags are set based on the summary text for use in scoring.
    """
    company = (company or "").strip()
    if not company:
        return CompanyEnrichment(error="empty company name")

    cache = get_cache()
    cached = cache.get("wikipedia", company.lower())
    if cached is not None:
        try:
            return CompanyEnrichment(**cached)
        except TypeError:
            # Model shape changed; fall through and re-fetch
            pass

    result = CompanyEnrichment()
    search = _search(company)
    if not search:
        result.error = "search failed"
        cache.set("wikipedia", company.lower(), result.__dict__)
        return result

    hits = search.get("query", {}).get("search", [])
    if not hits:
        cache.set("wikipedia", company.lower(), result.__dict__)
        return result

    # Look for a title that starts with or closely matches the company name.
    company_lower = company.lower()
    chosen = None
    for h in hits:
        title = h.get("title", "")
        if title.lower() == company_lower or title.lower().startswith(company_lower):
            chosen = title
            break

    if chosen:
        summary = _summary(chosen)
        if summary and summary.get("type") == "standard":
            extract = summary.get("extract", "") or ""
            result.has_wikipedia_page = True
            result.wikipedia_title = summary.get("title", chosen)
            result.wikipedia_summary = extract[:1200]
            content_urls = summary.get("content_urls", {}) or {}
            desktop = content_urls.get("desktop", {}) or {}
            result.wikipedia_url = desktop.get("page", f"https://en.wikipedia.org/wiki/{requests.utils.quote(chosen)}")
            result.matches_multifamily = _has_any(extract, MULTIFAMILY_KW)
            result.matches_property_mgmt = _has_any(extract, PROP_MGMT_KW)
            result.matches_real_estate_owner = _has_any(extract, RE_OWNER_KW)
            result.matches_adjacent = _has_any(extract, ADJACENT_KW)
            result.multi_property_signals = _has_scale_signal(extract)
            cache.set("wikipedia", company.lower(), result.__dict__)
            return result

    # No exact standalone page — see if the company is at least mentioned in a top hit.
    top = hits[0]
    snippet = top.get("snippet", "") or ""
    if company_lower in snippet.lower():
        result.parent_mention_only = True
        result.wikipedia_title = top.get("title")
        result.wikipedia_summary = re.sub(r"<[^>]+>", "", snippet)[:500]
        result.wikipedia_url = f"https://en.wikipedia.org/wiki/{requests.utils.quote(top.get('title', ''))}"

    cache.set("wikipedia", company.lower(), result.__dict__)
    return result
