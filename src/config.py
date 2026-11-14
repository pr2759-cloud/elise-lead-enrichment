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
# Learned weights (v2). `python -m src.main learn ... --write` saves weights
# fitted on real outcomes to this file; if it exists, it overrides the
# hand-set defaults above. Delete the file to go back to the defaults.
# ---------------------------------------------------------------------------
LEARNED_WEIGHTS_PATH = os.getenv(
    "LEARNED_WEIGHTS_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "learned_weights.json"),
).strip()
WEIGHTS_SOURCE = "default (hand-set)"


def _load_learned_weights() -> None:
    """Override CATEGORY_WEIGHTS in place from LEARNED_WEIGHTS_PATH, if valid."""
    global WEIGHTS_SOURCE
    if not LEARNED_WEIGHTS_PATH or not os.path.exists(LEARNED_WEIGHTS_PATH):
        return
    import json
    try:
        with open(LEARNED_WEIGHTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        weights = {k: float(data["weights"][k]) for k in CATEGORY_WEIGHTS}
    except Exception:
        return  # malformed file: keep the defaults rather than crash a scheduled run
    if abs(sum(weights.values()) - 1.0) > 1e-3 or min(weights.values()) < 0:
        return
    CATEGORY_WEIGHTS.update(weights)
    WEIGHTS_SOURCE = f"learned ({os.path.basename(LEARNED_WEIGHTS_PATH)}, {data.get('n_labels', '?')} labels)"


_load_learned_weights()

# ---------------------------------------------------------------------------
# Action gate (v2): Sniper / Scout / Archivist.
# The pipeline decides what to do with a lead, not just how to score it.
#   send   (Sniper)    — strong, well-evidenced lead: email goes out
#   review (Scout)     — promising or uncertain: a human checks the draft first
#   silent (Archivist) — weak fit: record it, draft nothing, send nothing
# ---------------------------------------------------------------------------
SEND_MIN_SCORE = 80.0       # at or above: eligible for automatic send
REVIEW_MIN_SCORE = 60.0     # at or above: draft for human review
MIN_DATA_CONFIDENCE = 0.6   # below this share of resolved signals, never auto-send

# ---------------------------------------------------------------------------
# Routing (v2). Rules are checked in order; the first match wins.
# Conditions available (all must hold): tier_in, action_in, multi_property,
# has_trigger_30d, free_email, min_confidence, max_confidence.
# ---------------------------------------------------------------------------
ROUTING_RULES = [
    {"route": "data_review", "when": {"max_confidence": MIN_DATA_CONFIDENCE},
     "reason": "too few signals resolved to trust the score; enrich manually"},
    {"route": "nurture", "when": {"action_in": ["silent"]},
     "reason": "below the outreach bar; keep in CRM, no outreach"},
    {"route": "enterprise_ae", "when": {"tier_in": ["HOT", "WARM"], "multi_property": True},
     "reason": "multi-property operator; portfolio-wide deal"},
    {"route": "trigger_sdr", "when": {"tier_in": ["HOT", "WARM"], "has_trigger_30d": True},
     "reason": "fresh trigger event; speed matters"},
    {"route": "commercial_sdr", "when": {"tier_in": ["HOT", "WARM"]},
     "reason": "qualified single-site lead"},
    {"route": "nurture", "when": {},
     "reason": "no rule matched; default to nurture"},
]

# ---------------------------------------------------------------------------
# Outcomes (v2). Sales fills the `outcome` column; these values close the loop.
# ---------------------------------------------------------------------------
POSITIVE_OUTCOMES = {"replied", "meeting", "demo", "opportunity", "won"}
NEGATIVE_OUTCOMES = {"no_response", "not_interested", "unsubscribed", "bounced", "lost"}
MIN_LABELS_TO_LEARN = 30          # labelled leads needed before fitting weights
MIN_PER_CLASS_TO_LEARN = 5        # and at least this many of each outcome class
MIN_AUC_GAIN_TO_ADOPT = 0.02      # cross-validated gain needed to recommend new weights

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
