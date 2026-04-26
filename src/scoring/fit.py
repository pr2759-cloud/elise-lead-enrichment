"""Fit category: company type, role seniority, market tier, company scale."""
from __future__ import annotations

from ..config import CATEGORY_WEIGHTS, NEUTRAL_SUBSIGNAL_SCORE
from ..models import CategoryScore, CompanyEnrichment, Lead
from ..heuristics.email import seniority_score
from ..heuristics.market_tiers import market_tier_score


def _company_type_score(c: CompanyEnrichment) -> float:
    """Company type sub-signal, 0-10.

    Multifamily operator = 10
    Property management firm = 9
    Real estate owner/operator = 8
    Adjacent (hospitality, senior, student, co-living) = 6
    Other / unknown = 3
    """
    if c.matches_multifamily:
        return 10.0
    if c.matches_property_mgmt:
        return 9.0
    if c.matches_real_estate_owner:
        return 8.0
    if c.matches_adjacent:
        return 6.0
    return 3.0


def _company_scale_score(c: CompanyEnrichment) -> float:
    """Company scale sub-signal, 0-10.

    Standalone Wikipedia page = 10
    Parent-only mention = 7
    No Wikipedia presence = 4
    """
    if c.has_wikipedia_page:
        return 10.0
    if c.parent_mention_only:
        return 7.0
    return 4.0


def score_fit(lead: Lead, company: CompanyEnrichment) -> CategoryScore:
    cat = CategoryScore(name="fit", weight=CATEGORY_WEIGHTS["fit"])

    # Company Type
    if company.error is None and (
        company.has_wikipedia_page or company.parent_mention_only
    ):
        cat.sub_signals["company_type"] = _company_type_score(company)
    elif company.error is None:
        # No Wikipedia page at all — we can still score "other" rather than neutral
        cat.sub_signals["company_type"] = 3.0
    else:
        cat.sub_signals["company_type"] = NEUTRAL_SUBSIGNAL_SCORE
        cat.missing.append("company_type")

    # Role Seniority
    cat.sub_signals["role_seniority"] = seniority_score(lead.person_name, lead.person_email)

    # Market Tier
    cat.sub_signals["market_tier"] = market_tier_score(lead.city, lead.state, lead.country)

    # Company Scale
    if company.error is None:
        cat.sub_signals["company_scale"] = _company_scale_score(company)
    else:
        cat.sub_signals["company_scale"] = NEUTRAL_SUBSIGNAL_SCORE
        cat.missing.append("company_scale")

    return cat
