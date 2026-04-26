"""Sales insights block — scan-friendly summary organized around Fit/Value/Timing/Intent."""
from __future__ import annotations
from typing import List

from .heuristics.market_tiers import market_tier_label, market_tier_score
from .heuristics.seasonality import seasonality_label, seasonality_score
from .models import (
    CompanyEnrichment, EnrichedLead, Lead, LeadScore, LocationEnrichment,
    MarketEnrichment, NewsEnrichment,
)


def _fit_line(lead: Lead, company: CompanyEnrichment, score: LeadScore) -> str:
    parts: List[str] = []

    # Company type inference — lead with the implication
    if company.matches_multifamily:
        parts.append(f"{lead.company} is a multifamily operator (highest-fit ICP)")
    elif company.matches_property_mgmt:
        parts.append(f"{lead.company} is a property management firm (strong ICP)")
    elif company.matches_real_estate_owner:
        parts.append(f"{lead.company} is a real estate owner/operator (solid ICP fit)")
    elif company.matches_adjacent:
        parts.append(f"{lead.company} is in an adjacent vertical — pitch may need adapting")
    elif company.has_wikipedia_page:
        parts.append(f"{lead.company} is established but industry fit is unclear — qualify before pitching")
    elif company.parent_mention_only:
        parts.append(f"{lead.company} appears to be a subsidiary — decision-making authority may sit above")
    else:
        parts.append(f"{lead.company} has no verified web presence — treat as unqualified until confirmed")

    # Role inference
    role_score = score.fit.sub_signals.get("role_seniority", 0)
    if role_score >= 10:
        parts.append(f"{lead.person_name} is likely a decision-maker — skip to business case")
    elif role_score >= 7:
        parts.append(f"{lead.person_name} is mid-level — likely an influencer, not final sign-off")
    elif role_score <= 3:
        parts.append("contact looks like a shared alias or IC — find a named stakeholder if possible")

    # Market inference
    tier_score = market_tier_score(lead.city, lead.state, lead.country)
    tier_label = market_tier_label(lead.city, lead.state, lead.country)
    if tier_score >= 10:
        parts.append(f"{lead.city} is a Tier 1 gateway market — competitive, but high ACV potential")
    elif tier_score >= 7:
        parts.append(f"{lead.city} is a strong secondary market — solid pipeline value")
    else:
        parts.append(f"{lead.city} is a {tier_label} market — lower priority unless volume is large")

    return "; ".join(parts)


def _value_line(market: MarketEnrichment, location: LocationEnrichment, company: CompanyEnrichment) -> str:
    parts: List[str] = []

    if market.renter_share is not None and market.median_gross_rent is not None:
        renter_pct = int(market.renter_share * 100)
        rent = int(market.median_gross_rent)
        if market.renter_share >= 0.60:
            parts.append(
                f"Dense rental market: {renter_pct}% renter-occupied at ${rent:,}/mo median — "
                f"operator likely managing high occupancy pressure, receptive to automation"
            )
        elif market.renter_share >= 0.40:
            parts.append(
                f"Mixed market: {renter_pct}% renter-occupied at ${rent:,}/mo — "
                f"moderate automation urgency"
            )
        else:
            parts.append(
                f"Owner-heavy market ({renter_pct}% renter-occupied) — smaller rental management footprint"
            )
    elif market.median_gross_rent is not None:
        parts.append(f"Median rent ${int(market.median_gross_rent):,}/mo in ZIP {market.zip_code}")

    if location.walk_score is not None:
        if location.walk_score >= 90:
            parts.append(f"Walker's paradise (Walk Score {location.walk_score}) — premium unit pricing likely, high leasing velocity")
        elif location.walk_score >= 70:
            parts.append(f"Walkable area (Walk Score {location.walk_score}) — above-average leasing demand")
        elif location.walk_score < 50:
            parts.append(f"Car-dependent area (Walk Score {location.walk_score}) — leasing pace likely slower")

    if company.multi_property_signals:
        parts.append("multi-property portfolio — pitch multi-site rollout to maximize deal size")

    return "; ".join(parts) if parts else "limited market data — value case will need to be built manually"


def _timing_line(news: NewsEnrichment) -> str:
    parts: List[str] = []

    # Trigger event inference — lead with the why-now implication
    if news.trigger_headline_30d:
        velocity = f"{news.articles_30d} articles in 30d" if news.articles_30d else "recent coverage"
        parts.append(
            f"Why now: active news cycle ({velocity}) — operators in expansion mode are "
            f"2-3x more receptive; lead with the trigger: \"{news.trigger_headline_30d}\""
        )
    elif news.trigger_headline_90d:
        parts.append(
            f"Recent trigger (90d): \"{news.trigger_headline_90d}\" — momentum may still be live; "
            f"reference it to show you've done your homework"
        )
    elif news.articles_30d:
        parts.append(
            f"{news.articles_30d} articles in 30d but no single acquisition/expansion trigger — "
            f"something is moving; mention their recent activity to warm the opener"
        )
    elif news.articles_90d:
        parts.append(
            f"Low recent news ({news.articles_90d} articles in 90d) — no obvious trigger; "
            f"lean on seasonality and market context instead"
        )
    else:
        parts.append("no news signal detected — cold outreach, rely on market fit and seasonality")

    # Seasonality inference
    s_score = seasonality_score()
    if s_score >= 10:
        parts.append("peak leasing season (Apr-Aug): operators are stretched thin — automation pitch lands hardest now")
    elif s_score >= 7:
        parts.append("shoulder season: good window to get in front of decision-makers before the next peak")
    else:
        parts.append("off-season: operators are planning mode — good for planting seeds, weaker for urgency close")

    return "; ".join(parts)


def _intent_line(lead: Lead, company: CompanyEnrichment, news: NewsEnrichment) -> str:
    from .heuristics.email import is_free_provider, extract_domain
    parts: List[str] = []

    # Email quality inference
    if lead.person_email and not is_free_provider(lead.person_email):
        domain = extract_domain(lead.person_email)
        parts.append(
            f"Company-domain email (@{domain}) — this is a real business contact, "
            f"not a prospecting alias; expect higher reply rate"
        )
    elif lead.person_email and is_free_provider(lead.person_email):
        parts.append(
            "Free-provider email — contact quality is uncertain; "
            "verify identity before investing heavy personalization"
        )

    # News / web presence inference
    if news.has_tech_news:
        parts.append(
            "tech/digital news presence — company is already investing in PropTech direction; "
            "skip the 'why tech' objection, go straight to ROI"
        )
    elif news.articles_90d:
        parts.append("general news presence — company is active and visible, not a ghost account")
    elif company.has_wikipedia_page:
        parts.append("established Wikipedia presence — credible operator, but digital-investment appetite unknown")
    else:
        parts.append("minimal digital footprint — lower confidence this is an active decision-maker")

    return "; ".join(parts) if parts else "limited intent signals — treat as cold until more data available"


def _risks(lead: Lead, company: CompanyEnrichment, score: LeadScore,
           market: MarketEnrichment, location: LocationEnrichment) -> List[str]:
    from .heuristics.email import is_free_provider
    flags: List[str] = []

    if lead.person_email and is_free_provider(lead.person_email):
        flags.append("Free-email contact — verify legitimacy before deep outreach")

    if score.fit.sub_signals.get("company_scale", 10) <= 4 and not company.parent_mention_only:
        flags.append(f"No Wikipedia presence for {lead.company} — confirm this is the real company before outreach")

    if score.fit.sub_signals.get("market_tier", 10) <= 4:
        flags.append(f"International lead ({lead.city}) — confirm product readiness for this market before pitching")

    if seasonality_score() <= 4:
        flags.append("Off-season — expect slower response cycles; budget for longer nurture timeline")

    if location.error is not None and market.error is None:
        flags.append("Property address didn't geocode (WalkScore failed) — confirm address is valid before site visit")

    return flags


def _talking_points(lead: Lead, company: CompanyEnrichment, news: NewsEnrichment,
                    market: MarketEnrichment, location: LocationEnrichment) -> List[str]:
    points: List[str] = []

    if news.trigger_headline_30d:
        points.append(
            f"Open with the news: \"Saw the headline — '{news.trigger_headline_30d}' — "
            f"companies in active expansion mode often find leasing automation pays back fastest.\""
        )
    elif news.trigger_headline_90d:
        points.append(
            f"Reference recent activity: \"Noticed {lead.company} has been making moves — "
            f"what does that mean for your leasing team's workload?\""
        )

    if company.multi_property_signals:
        points.append(
            "Lead with portfolio scale: \"For operators running multiple properties, "
            "the ROI compounds — one integration rolls out across every site.\""
        )

    if location.walk_score and location.walk_score >= 80:
        points.append(
            f"Mention location premium: \"Walk Score {location.walk_score} means high leasing velocity — "
            f"automation keeps response times tight when demand spikes.\""
        )

    if market.renter_share and market.renter_share >= 0.60:
        points.append(
            f"Market density angle: \"{int(market.renter_share * 100)}% renter-occupied in this ZIP — "
            f"that's a deep pool; leasing speed is a competitive differentiator here.\""
        )

    if not points:
        points.append(
            "No strong personalization hooks — use the ICP pitch: "
            "\"Elise helps multifamily operators cut leasing response time without adding headcount.\""
        )
    return points


def build_insights(enriched: "EnrichedLead") -> str:
    """Format the insights block as a readable multi-line string."""
    lead = enriched.lead
    score = enriched.score
    resolved = score.total_signals_count - score.missing_signals_count
    risks = _risks(lead, enriched.company, score, enriched.market, enriched.location)
    lines = [
        f"Score: {score.final_score:.1f}/100 — {score.tier}",
        f"Fit:    {_fit_line(lead, enriched.company, score)}",
        f"Value:  {_value_line(enriched.market, enriched.location, enriched.company)}",
        f"Timing: {_timing_line(enriched.news)}",
        f"Intent: {_intent_line(lead, enriched.company, enriched.news)}",
        "Talking points: " + " | ".join(
            _talking_points(lead, enriched.company, enriched.news, enriched.market, enriched.location)
        ),
        "Risks:  " + (" | ".join(risks) if risks else "none flagged"),
        f"Data confidence: {resolved}/{score.total_signals_count} sub-signals resolved",
    ]
    return "\n".join(lines)
