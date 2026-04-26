"""Top-level scoring engine: runs all four categories and assembles a LeadScore."""
from __future__ import annotations

from ..models import (
    CompanyEnrichment, Lead, LeadScore, LocationEnrichment,
    MarketEnrichment, NewsEnrichment,
)
from .fit import score_fit
from .value import score_value
from .timing import score_timing
from .intent import score_intent


def score_lead(
    lead: Lead,
    company: CompanyEnrichment,
    news: NewsEnrichment,
    market: MarketEnrichment,
    location: LocationEnrichment,
) -> LeadScore:
    return LeadScore(
        fit=score_fit(lead, company),
        value=score_value(market, location, company),
        timing=score_timing(news),
        intent=score_intent(lead, company, news),
    )
