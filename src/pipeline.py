"""Pipeline orchestrator: enrich a single lead end-to-end."""
from __future__ import annotations
import logging
from typing import List

from .enrich.wikipedia import enrich_company_wikipedia
from .enrich.newsapi import enrich_news
from .enrich.census import enrich_market
from .enrich.walkscore import enrich_location
from .gating import decide
from .insights import build_insights
from .routing import RouteContext, route_lead
from .models import EnrichedLead, Lead
from .outreach.email_drafter import draft_email
from .scoring.engine import score_lead

log = logging.getLogger(__name__)


def enrich_one(lead: Lead) -> EnrichedLead:
    """Run the full enrichment pipeline on a single lead.

    Returns an EnrichedLead in all cases — individual API failures are captured
    in the sub-enrichment's .error field and reflected in the score's missing
    signals count; they never abort the pipeline.
    """
    errors: List[str] = []

    company = enrich_company_wikipedia(lead.company)
    if company.error:
        errors.append(f"wikipedia: {company.error}")

    news = enrich_news(lead.company)
    if news.error:
        errors.append(f"newsapi: {news.error}")

    market = enrich_market(lead.property_address)
    if market.error:
        errors.append(f"census: {market.error}")

    location = enrich_location(lead.property_address, lead.city, lead.state, lead.country)
    if location.error:
        errors.append(f"walkscore: {location.error}")

    score = score_lead(lead, company, news, market, location)

    # Build insights first — the LLM polish step uses them as grounding context.
    enriched = EnrichedLead(
        lead=lead, company=company, news=news, market=market, location=location,
        score=score, insights="", email_subject="", email_body="", errors=errors,
    )
    enriched.insights = build_insights(enriched)

    # v2: decide before drafting. Silent leads get no draft at all, which also
    # saves the LLM call.
    decision = decide(lead, score)
    enriched.action, enriched.action_reason = decision.action, decision.reason
    route = route_lead(RouteContext(lead, score, company, news, decision.action))
    enriched.route, enriched.route_reason = route.route, route.reason

    if decision.action != "silent":
        subject, body = draft_email(lead, company, news, market, location, score, enriched.insights)
        enriched.email_subject = subject
        enriched.email_body = body

    log.info(
        "Scored %s (%s) → %.1f %s [%d/%d signals, %d errors] → %s via %s",
        lead.company, lead.person_email, score.final_score, score.tier,
        score.total_signals_count - score.missing_signals_count,
        score.total_signals_count, len(errors), decision.action, route.route,
    )
    return enriched
