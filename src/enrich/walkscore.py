"""WalkScore enrichment: walk/transit/bike scores for a property address.

WalkScore requires latitude/longitude, so we geocode first. We use the US
Census Bureau's free geocoder as the primary source (no key, no rate-limit
issues, reliable for US addresses) and fall back to OpenStreetMap's Nominatim
for non-US addresses.
"""
from __future__ import annotations
import logging
import time
from typing import Optional, Tuple

from ..config import WALKSCORE_ENDPOINT, WALKSCORE_KEY
from ..http_client import HTTPError, get_json
from ..models import LocationEnrichment
from ..cache import get_cache

log = logging.getLogger(__name__)

CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


def _geocode_census(address: str, city: str, state: str) -> Optional[Tuple[float, float]]:
    """Resolve a US address → (lat, lon) via the US Census Geocoder.

    Free, no key, no rate-limit policy. Returns None for non-US or unresolvable
    addresses, letting the caller fall back to Nominatim.
    """
    q_parts = [p for p in (address, city, state) if p]
    one_line = ", ".join(q_parts)
    params = {
        "address": one_line,
        "benchmark": "Public_AR_Current",
        "format": "json",
    }
    try:
        data = get_json(CENSUS_GEOCODER_URL, params=params) or {}
        matches = (data.get("result") or {}).get("addressMatches") or []
        if not matches:
            return None
        coords = matches[0].get("coordinates") or {}
        lat = float(coords["y"])
        lon = float(coords["x"])
        return (lat, lon)
    except (HTTPError, KeyError, ValueError, TypeError) as e:
        log.debug("Census geocoder failed for %s: %s", one_line, e)
        return None


def _geocode_nominatim(address: str, city: str, state: str, country: str) -> Optional[Tuple[float, float]]:
    """Fallback geocoder via OpenStreetMap's Nominatim. Used for non-US addresses."""
    q_parts = [p for p in (address, city, state, country) if p]
    q = ", ".join(q_parts)
    params = {"q": q, "format": "json", "limit": 1, "addressdetails": 0}
    try:
        # Nominatim asks for <= 1 request per second
        time.sleep(1.0)
        hits = get_json(NOMINATIM_URL, params=params) or []
        if not hits:
            return None
        lat = float(hits[0]["lat"])
        lon = float(hits[0]["lon"])
        return (lat, lon)
    except (HTTPError, KeyError, ValueError) as e:
        log.debug("Nominatim geocoder failed for %s: %s", q, e)
        return None


def _geocode(address: str, city: str, state: str, country: str) -> Optional[Tuple[float, float]]:
    """Try Census geocoder first for US addresses, then Nominatim as fallback."""
    country_upper = (country or "").strip().upper()
    is_us = country_upper in {"US", "USA", "UNITED STATES", ""}

    if is_us:
        coords = _geocode_census(address, city, state)
        if coords is not None:
            return coords
        # Census failed — try Nominatim as backup
        log.debug("Census geocoder returned nothing, trying Nominatim")

    return _geocode_nominatim(address, city, state, country)


def enrich_location(address: str, city: str, state: str, country: str = "US") -> LocationEnrichment:
    """Best-effort Walk/Transit/Bike score lookup for the property."""
    result = LocationEnrichment()

    if not WALKSCORE_KEY:
        result.error = "no WALKSCORE_KEY configured"
        return result

    cache_key = f"{address}|{city}|{state}|{country}".lower()
    cache = get_cache()
    cached = cache.get("walkscore", cache_key)
    if cached is not None:
        try:
            return LocationEnrichment(**cached)
        except TypeError:
            pass

    coords = _geocode(address, city, state, country)
    if coords is None:
        result.error = "geocoding failed"
        cache.set("walkscore", cache_key, result.__dict__)
        return result

    lat, lon = coords
    params = {
        "format": "json",
        "address": f"{address}, {city}, {state}",
        "lat": lat,
        "lon": lon,
        "transit": 1,
        "bike": 1,
        "wsapikey": WALKSCORE_KEY,
    }
    try:
        data = get_json(WALKSCORE_ENDPOINT, params=params) or {}
    except HTTPError as e:
        log.warning("WalkScore call failed for %s: %s", address, e)
        result.error = f"walkscore fetch failed: {e}"
        cache.set("walkscore", cache_key, result.__dict__)
        return result

    # WalkScore status 1 = success
    status = data.get("status")
    if status == 1:
        if data.get("walkscore") is not None:
            result.walk_score = int(data["walkscore"])
        transit = data.get("transit") or {}
        if transit.get("score") is not None:
            result.transit_score = int(transit["score"])
        bike = data.get("bike") or {}
        if bike.get("score") is not None:
            result.bike_score = int(bike["score"])
    else:
        result.error = f"walkscore status {status}: {data.get('description', '')}"

    cache.set("walkscore", cache_key, result.__dict__)
    return result
