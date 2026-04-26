"""Static mapping of US metro areas to market tiers used by the Fit category."""
from __future__ import annotations
from typing import Optional


TIER_1 = {
    # Core gateway markets
    "new york", "new york city", "nyc", "brooklyn", "manhattan", "queens", "bronx",
    "san francisco", "oakland", "berkeley", "san jose",
    "los angeles", "la", "santa monica", "pasadena", "long beach",
    "chicago",
    "boston", "cambridge", "somerville",
    "washington", "washington dc", "d.c.", "dc",
    "seattle", "bellevue",
    "austin",
    "miami", "miami beach",
}

TIER_2 = {
    "atlanta",
    "denver", "boulder",
    "nashville",
    "charlotte",
    "portland",
    "dallas", "fort worth", "plano", "irving",
    "houston",
    "phoenix", "scottsdale", "tempe",
    "san diego",
    "minneapolis", "saint paul", "st. paul", "st paul",
    "philadelphia",
    "detroit",
    "tampa", "st. petersburg",
    "orlando",
    "raleigh", "durham",
    "salt lake city",
    "columbus",
    "kansas city",
    "indianapolis",
    "pittsburgh",
    "sacramento",
    "las vegas",
    "baltimore",
    "cincinnati",
    "cleveland",
    "st. louis", "st louis", "saint louis",
    "milwaukee",
    "new orleans",
    "jacksonville",
    "richmond",
    "san antonio",
}


def market_tier_score(city: str, state: str = "", country: str = "US") -> float:
    """Fit sub-signal: 0-10 based on the strength of the metro.

    Tier 1 gateway markets: 10
    Tier 2 strong secondary: 7
    Other US markets: 5
    International: 4
    """
    if country and country.strip().upper() not in {"US", "USA", "UNITED STATES"}:
        return 4.0
    if not city:
        return 5.0
    c = city.strip().lower()
    if c in TIER_1:
        return 10.0
    if c in TIER_2:
        return 7.0
    return 5.0


def market_tier_label(city: str, state: str = "", country: str = "US") -> str:
    score = market_tier_score(city, state, country)
    return {10.0: "Tier 1", 7.0: "Tier 2", 5.0: "Other US", 4.0: "International"}[score]
