"""Value category: rent level, lead volume potential, location premium, upsell."""
from __future__ import annotations

from ..config import CATEGORY_WEIGHTS, NEUTRAL_SUBSIGNAL_SCORE
from ..models import (
    CategoryScore, CompanyEnrichment, LocationEnrichment, MarketEnrichment,
)


def _rent_score(rent: float) -> float:
    if rent >= 2500: return 10.0
    if rent >= 1800: return 8.0
    if rent >= 1200: return 6.0
    return 3.0


def _lead_volume_score(renter_share: float, density_tier: str) -> float:
    high_renter = renter_share >= 0.60
    high_density = density_tier == "high"
    if high_renter and high_density:
        return 10.0
    if high_renter or high_density:
        return 7.0
    return 3.0


def _location_premium_score(walk: int) -> float:
    if walk >= 80: return 10.0
    if walk >= 60: return 7.0
    if walk >= 40: return 5.0
    return 3.0


def _upsell_score(c: CompanyEnrichment) -> float:
    if c.multi_property_signals:
        return 10.0
    if c.has_wikipedia_page:
        return 6.0
    if c.parent_mention_only:
        return 5.0
    return 3.0


def score_value(
    market: MarketEnrichment,
    location: LocationEnrichment,
    company: CompanyEnrichment,
) -> CategoryScore:
    cat = CategoryScore(name="value", weight=CATEGORY_WEIGHTS["value"])

    # Rent Level
    if market.median_gross_rent is not None:
        cat.sub_signals["rent_level"] = _rent_score(market.median_gross_rent)
    else:
        cat.sub_signals["rent_level"] = NEUTRAL_SUBSIGNAL_SCORE
        cat.missing.append("rent_level")

    # Lead Volume Potential
    if market.renter_share is not None and market.density_tier is not None:
        cat.sub_signals["lead_volume"] = _lead_volume_score(
            market.renter_share, market.density_tier
        )
    else:
        cat.sub_signals["lead_volume"] = NEUTRAL_SUBSIGNAL_SCORE
        cat.missing.append("lead_volume")

    # Location Premium
    if location.walk_score is not None:
        cat.sub_signals["location_premium"] = _location_premium_score(location.walk_score)
    else:
        cat.sub_signals["location_premium"] = NEUTRAL_SUBSIGNAL_SCORE
        cat.missing.append("location_premium")

    # Upsell Potential
    if company.error is None:
        cat.sub_signals["upsell_potential"] = _upsell_score(company)
    else:
        cat.sub_signals["upsell_potential"] = NEUTRAL_SUBSIGNAL_SCORE
        cat.missing.append("upsell_potential")

    return cat
