"""US Census ACS enrichment: median rent, renter share, population for a ZIP.

Strategy: the Census API periodically rotates its "current" ACS5 vintage. If
one vintage returns an HTML error page (which parses as invalid JSON), we try
the next vintage down. This keeps the pipeline resilient to Census's release
cycle without requiring code changes every year.
"""
from __future__ import annotations
import logging
import re
from typing import List, Optional

import requests

from ..config import CENSUS_KEY, HTTP_TIMEOUT_SECONDS, HTTP_USER_AGENT
from ..models import MarketEnrichment
from ..cache import get_cache

log = logging.getLogger(__name__)


# ACS 5-year variable codes (stable across vintages):
#   B25064_001E  Median gross rent
#   B25003_003E  Renter-occupied housing units
#   B25003_001E  Total occupied housing units (denominator)
#   B01003_001E  Total population
CENSUS_VARIABLES = "B25064_001E,B25003_003E,B25003_001E,B01003_001E"

# Ordered list of vintages to try, newest first. The Census API sometimes
# returns HTML error pages for one vintage while another works — we try them
# in order until we get parseable JSON.
CENSUS_VINTAGES = ["2023", "2022", "2021"]

ZIP_RE = re.compile(r"\b(\d{5})(?:-\d{4})?\b")


def extract_zip(property_address: str) -> Optional[str]:
    """Pull a 5-digit ZIP out of a US address string."""
    if not property_address:
        return None
    m = ZIP_RE.search(property_address)
    return m.group(1) if m else None


def _density_tier(population: Optional[int]) -> Optional[str]:
    """Crude density bucket from ZIP population (ZCTAs are small, so this is a proxy)."""
    if population is None:
        return None
    if population >= 30000:
        return "high"
    if population >= 10000:
        return "mid"
    return "low"


def _fetch_vintage(zip_code: str, vintage: str) -> Optional[List[list]]:
    """Call one vintage of the Census ACS5 API. Returns parsed JSON or None on failure.

    We use requests directly (not the retry client) because we want to log the
    raw response body when it's not JSON — that's the biggest signal for
    diagnosing what went wrong. Retrying the same vintage rarely helps;
    switching vintages is what fixes it.
    """

# Module-level session so cookies (e.g. Census's TSxxx bot-mitigation cookie) persist
# across calls. Without this, every request arrives cookie-less and Census
# occasionally responds with a non-JSON challenge page on the first call per
# process. Using a Session makes the second-and-onward calls always succeed.
_session: Optional[requests.Session] = None
_session_warmed: bool = False


def _get_session() -> requests.Session:
    global _session, _session_warmed
    if _session is None:
        s = requests.Session()
        # Use browser-style headers. Census's bot-mitigation layer is more
        # permissive with realistic Accept/Accept-Encoding/Accept-Language
        # headers than with a bare curl-style request.
        s.headers.update({
            "User-Agent": HTTP_USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
        })
        _session = s
    if not _session_warmed:
        # Warm the session by making a throwaway call that triggers the
        # cookie-setting flow. If it fails, the real call is still attempted.
        try:
            _session.get("https://api.census.gov/data/2023/acs/acs5/variables.json",
                         timeout=HTTP_TIMEOUT_SECONDS)
        except Exception:
            pass
        _session_warmed = True
    return _session


def _fetch_vintage(zip_code: str, vintage: str) -> Optional[List[list]]:
    """Call one vintage of the Census ACS5 API. Returns parsed JSON or None on failure.

    Uses a persistent Session so Census's session cookie is carried forward,
    which prevents the non-JSON challenge response on repeat calls.
    """
    url = f"https://api.census.gov/data/{vintage}/acs/acs5"
    params = {
        "get": CENSUS_VARIABLES,
        "for": f"zip code tabulation area:{zip_code}",
    }
    if CENSUS_KEY:
        params["key"] = CENSUS_KEY

    session = _get_session()
    try:
        r = session.get(url, params=params, timeout=HTTP_TIMEOUT_SECONDS)
    except Exception as e:
        log.debug("Census %s network error for ZIP %s: %s", vintage, zip_code, e)
        return None

    if r.status_code != 200:
        log.debug("Census %s returned HTTP %d for ZIP %s: %s",
                  vintage, r.status_code, zip_code, r.text[:200])
        return None

    body = r.text.strip()
    if not body:
        log.debug("Census %s returned empty body for ZIP %s", vintage, zip_code)
        return None

    # Sniff for HTML before trying to parse JSON — produces a cleaner log line.
    if body.lstrip().startswith("<"):
        log.debug("Census %s returned HTML (likely error page) for ZIP %s: %s",
                  vintage, zip_code, body[:200])
        return None

    try:
        return r.json()
    except ValueError as e:
        log.debug("Census %s returned non-JSON for ZIP %s: %s | body=%s",
                  vintage, zip_code, e, body[:200])
        return None


def enrich_market(property_address: str) -> MarketEnrichment:
    """Best-effort market enrichment for the ZIP of the property address."""
    zip_code = extract_zip(property_address)
    if not zip_code:
        return MarketEnrichment(error="could not extract ZIP from address")

    cache = get_cache()
    cached = cache.get("census", zip_code)
    if cached is not None:
        try:
            return MarketEnrichment(**cached)
        except TypeError:
            pass

    result = MarketEnrichment(zip_code=zip_code)
    data: Optional[List[list]] = None
    used_vintage: Optional[str] = None

    for vintage in CENSUS_VINTAGES:
        data = _fetch_vintage(zip_code, vintage)
        if data:
            used_vintage = vintage
            break

    if not data or len(data) < 2:
        vintages_tried = ", ".join(CENSUS_VINTAGES)
        log.warning("Census call failed for ZIP %s (tried vintages: %s)",
                    zip_code, vintages_tried)
        result.error = f"no parseable census response across vintages {vintages_tried}"
        cache.set("census", zip_code, result.__dict__)
        return result

    log.debug("Census used vintage %s for ZIP %s", used_vintage, zip_code)

    headers_row, values_row = data[0], data[1]
    values = dict(zip(headers_row, values_row))

    def _num(v) -> Optional[float]:
        try:
            f = float(v)
            if f < 0:  # Census uses negatives as nulls
                return None
            return f
        except (TypeError, ValueError):
            return None

    median_rent = _num(values.get("B25064_001E"))
    renter_occ = _num(values.get("B25003_003E"))
    total_occ = _num(values.get("B25003_001E"))
    population = _num(values.get("B01003_001E"))

    result.median_gross_rent = median_rent
    if renter_occ is not None and total_occ and total_occ > 0:
        result.renter_share = round(renter_occ / total_occ, 4)
    if population is not None:
        result.population = int(population)
        result.density_tier = _density_tier(int(population))

    cache.set("census", zip_code, result.__dict__)
    return result
