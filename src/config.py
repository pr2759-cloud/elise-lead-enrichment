"""Central configuration: weights, thresholds, API endpoints, keyword lists."""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Dict

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv optional for demo mode


# ---------------------------------------------------------------------------
# Category weights (see docs/plan §5.1). Must sum to 1.0.
# ---------------------------------------------------------------------------
CATEGORY_WEIGHTS: Dict[str, float] = {
    "fit": 0.30,
    "value": 0.25,
    "timing": 0.25,
    "intent": 0.20,
}
assert abs(sum(CATEGORY_WEIGHTS.values()) - 1.0) < 1e-9, "Category weights must sum to 1.0"

# ---------------------------------------------------------------------------
# Tier thresholds on the final 0-100 score.
# ---------------------------------------------------------------------------
TIER_THRESHOLDS = {
    "HOT": 80,
    "WARM": 60,
    "COOL": 40,
    "COLD": 0,
}

# ---------------------------------------------------------------------------
# Neutral fallback score for a missing sub-signal (see docs/plan §5.7).
# ---------------------------------------------------------------------------
NEUTRAL_SUBSIGNAL_SCORE = 5.0

# ---------------------------------------------------------------------------
# API credentials and endpoints
# ---------------------------------------------------------------------------
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY", "").strip()
WALKSCORE_KEY = os.getenv("WALKSCORE_KEY", "").strip()
CENSUS_KEY = os.getenv("CENSUS_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
LEADS_SHEET_ID = os.getenv("LEADS_SHEET_ID", "").strip()
LEADS_WORKSHEET_NAME = os.getenv("LEADS_WORKSHEET_NAME", "Leads").strip()

CACHE_PATH = os.getenv("CACHE_PATH", "./cache.db").strip()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"
CENSUS_ENDPOINT = "https://api.census.gov/data/2022/acs/acs5"
CENSUS_ZCTA_ENDPOINT = "https://api.census.gov/data/2022/acs/acs5"
WALKSCORE_ENDPOINT = "https://api.walkscore.com/score"

HTTP_TIMEOUT_SECONDS = 10
# User-Agent for most APIs. For Nominatim, we need a more specific one with valid contact.
HTTP_USER_AGENT = "EliseAI-LeadEnrichment/1.0 (https://github.com/eliseai/lead-enrichment)"

# ---------------------------------------------------------------------------
# Cache TTLs in seconds
# ---------------------------------------------------------------------------
CACHE_TTL = {
    "wikipedia": 30 * 24 * 3600,   # 30 days
    "newsapi":   1 * 24 * 3600,    # 1 day
    "census":    365 * 24 * 3600,  # 1 year
    "walkscore": 90 * 24 * 3600,   # 90 days
}


@dataclass(frozen=True)
class RuntimeFlags:
    use_llm_polish: bool
    have_newsapi: bool
    have_walkscore: bool
    have_census: bool


def runtime_flags() -> RuntimeFlags:
    """Snapshot of which capabilities are available at runtime."""
    return RuntimeFlags(
        use_llm_polish=bool(ANTHROPIC_API_KEY),
        have_newsapi=bool(NEWSAPI_KEY),
        have_walkscore=bool(WALKSCORE_KEY),
        have_census=True,  # Census works without a key for light use
    )
