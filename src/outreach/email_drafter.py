"""Email drafter: selects template based on dominant category and fills it in.

If ANTHROPIC_API_KEY is configured, a single Claude Haiku call polishes the
opening hook for stronger personalization. Without it, the tool works with
pure templates.
"""
from __future__ import annotations
import logging
from typing import Tuple

from ..config import ANTHROPIC_API_KEY
from ..models import (
    CompanyEnrichment, EnrichedLead, Lead, LeadScore, LocationEnrichment,
    MarketEnrichment, NewsEnrichment,
)
from .templates import TEMPLATES

log = logging.getLogger(__name__)

SENDER_NAME = "Alex, EliseAI"


def _pick_template_key(
    score: LeadScore, news: NewsEnrichment, market: MarketEnrichment,
    location: LocationEnrichment, company: CompanyEnrichment,
) -> str:
    """Select the template whose dominant signal is strongest for this lead."""
    # 1. A recent high-signal news trigger in the last 30 days is the most
    #    compelling personalization hook we have — always prefer it.
    if news.trigger_headline_30d:
        return "trigger_event"

    # 2. If the Fit score is dominant AND the company is clearly scaled, use the
    #    Scale template.
    cat_scores = {
        "fit": score.fit.average,
        "value": score.value.average,
        "timing": score.timing.average,
    }
    dominant = max(cat_scores, key=cat_scores.get)

    if dominant == "value" and (
        (location.walk_score and location.walk_score >= 70)
        or (market.median_gross_rent and market.median_gross_rent >= 2000)
    ):
        return "premium_market"

    if dominant == "fit" and (company.has_wikipedia_page and (
        company.multi_property_signals or score.fit.average >= 8.5
    )):
        return "scale"

    if dominant == "timing" and score.timing.sub_signals.get("seasonality", 0) >= 10:
        return "seasonal"

    # Fall back to generic.
    return "generic"


def _short_trigger(headline: str) -> str:
    """Shorten a news headline for the subject line."""
    h = (headline or "").strip()
    if len(h) <= 60:
        return h
    return h[:57].rstrip() + "..."


def _format_template(
    key: str, lead: Lead, company: CompanyEnrichment, news: NewsEnrichment,
    market: MarketEnrichment, location: LocationEnrichment,
) -> Tuple[str, str]:
    subject_tpl, body_tpl = TEMPLATES[key]

    # Build a market fact string when we have one
    market_fact_parts = []
    if market.renter_share is not None:
        market_fact_parts.append(f"{market.renter_share * 100:.0f}% renter-occupied")
    if market.median_gross_rent is not None:
        market_fact_parts.append(f"median rent around ${int(market.median_gross_rent):,}")
    if location.walk_score:
        market_fact_parts.append(f"Walk Score {location.walk_score}")
    market_fact = ", ".join(market_fact_parts) if market_fact_parts else f"{lead.city}-area fundamentals"

    property_ref = company.wikipedia_title if company.has_wikipedia_page else (
        lead.property_address.split(",", 1)[0] if lead.property_address else f"{lead.city} property"
    )

    ctx = {
        "first_name": lead.first_name,
        "company": lead.company,
        "property_ref": property_ref,
        "market_fact": market_fact,
        "trigger_headline": news.trigger_headline_30d or news.trigger_headline_90d or "",
        "trigger_headline_short": _short_trigger(
            news.trigger_headline_30d or news.trigger_headline_90d or lead.company
        ),
        "sender_name": SENDER_NAME,
    }
    return subject_tpl.format(**ctx), body_tpl.format(**ctx)


def _polish_with_llm(subject: str, body: str, enriched_context: str) -> Tuple[str, str]:
    """Optionally tighten the email with a single Claude call. Fail-safe: returns input on error."""
    if not ANTHROPIC_API_KEY:
        return subject, body
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        system = (
            "You are a top-performing SDR at EliseAI (AI leasing assistant for multifamily "
            "operators). You are polishing a cold outreach email draft. Rules: keep it "
            "under 110 words, keep the sender name and sign-off exactly as given, do not "
            "invent facts not in the provided context, keep the subject line under 60 "
            "characters, and return ONLY the polished email in this exact format:\n\n"
            "SUBJECT: <subject>\n\n<body>"
        )
        user = (
            f"CONTEXT (facts you may reference):\n{enriched_context}\n\n"
            f"DRAFT SUBJECT: {subject}\n\nDRAFT BODY:\n{body}"
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if "SUBJECT:" in text:
            after = text.split("SUBJECT:", 1)[1].strip()
            parts = after.split("\n", 1)
            new_subject = parts[0].strip()
            new_body = parts[1].strip() if len(parts) > 1 else body
            return new_subject, new_body
    except Exception as e:
        log.warning("LLM polish failed, falling back to template: %s", e)
    return subject, body


def draft_email(
    lead: Lead, company: CompanyEnrichment, news: NewsEnrichment,
    market: MarketEnrichment, location: LocationEnrichment,
    score: LeadScore, insights: str,
) -> Tuple[str, str]:
    """Return (subject, body) for the outreach email."""
    key = _pick_template_key(score, news, market, location, company)
    log.debug("Selected template '%s' for %s", key, lead.company)
    subject, body = _format_template(key, lead, company, news, market, location)
    subject, body = _polish_with_llm(subject, body, enriched_context=insights)
    return subject, body
