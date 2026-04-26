"""Offline end-to-end demo with pre-built enrichment data.

Bypasses the live API calls and shows what the tool's output looks like when
enrichment succeeds. Useful for verifying insights + email formatting without
needing any API keys configured.

Run:
    python tests/offline_demo.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.insights import build_insights
from src.models import (
    CompanyEnrichment, EnrichedLead, Lead, LocationEnrichment,
    MarketEnrichment, NewsEnrichment,
)
from src.outreach.email_drafter import draft_email
from src.scoring.engine import score_lead


SCENARIOS = [
    {
        "label": "HOT lead — large operator, peak-season trigger event",
        "lead": Lead(
            person_name="Jane Doe, VP of Leasing",
            person_email="jane.doe@greystar.com",
            company="Greystar",
            property_address="312 Peachtree St NE 30308",
            city="Atlanta", state="GA", country="US",
        ),
        "company": CompanyEnrichment(
            has_wikipedia_page=True,
            wikipedia_title="Greystar Real Estate Partners",
            wikipedia_url="https://en.wikipedia.org/wiki/Greystar_Real_Estate_Partners",
            wikipedia_summary="Greystar is the largest property management company for apartments in the United States, managing over 800,000 units...",
            matches_multifamily=True,
            matches_property_mgmt=True,
            multi_property_signals=True,
        ),
        "news": NewsEnrichment(
            articles_30d=8,
            articles_90d=23,
            trigger_headline_30d="Greystar acquires 1,200 units in Atlanta expansion",
            trigger_url="https://example.com/greystar-atlanta",
            has_tech_news=True,
            top_headline="Greystar announces AI-powered leasing platform partnership",
            top_url="https://example.com/greystar-ai",
        ),
        "market": MarketEnrichment(
            zip_code="30308",
            median_gross_rent=2040.0,
            renter_share=0.71,
            population=35200,
            density_tier="high",
        ),
        "location": LocationEnrichment(walk_score=88, transit_score=72, bike_score=65),
    },
    {
        "label": "WARM lead — solid ICP, no news hook",
        "lead": Lead(
            person_name="Carlos Ramirez",
            person_email="carlos@aimco.com",
            company="AIMCO",
            property_address="4582 S Ulster St 80237",
            city="Denver", state="CO", country="US",
        ),
        "company": CompanyEnrichment(
            has_wikipedia_page=True,
            wikipedia_title="Apartment Investment and Management Company",
            wikipedia_url="https://en.wikipedia.org/wiki/AIMCO",
            wikipedia_summary="Apartment Investment and Management Company is a real estate investment trust focused on multifamily apartment properties.",
            matches_multifamily=True,
            matches_real_estate_owner=True,
            multi_property_signals=True,
        ),
        "news": NewsEnrichment(articles_30d=1, articles_90d=4, has_tech_news=False,
                               top_headline="AIMCO reports quarterly earnings",
                               top_url="https://example.com/aimco-q2"),
        "market": MarketEnrichment(zip_code="80237", median_gross_rent=1850.0,
                                   renter_share=0.52, population=18400, density_tier="mid"),
        "location": LocationEnrichment(walk_score=58, transit_score=42, bike_score=55),
    },
    {
        "label": "COLD lead — small firm, free email, low-density market",
        "lead": Lead(
            person_name="Tom Wilson",
            person_email="tom.wilson@gmail.com",
            company="Wilson Properties",
            property_address="500 Oak Ave 45402",
            city="Dayton", state="OH", country="US",
        ),
        "company": CompanyEnrichment(error=None),  # No Wikipedia hit
        "news": NewsEnrichment(),  # No news hits
        "market": MarketEnrichment(zip_code="45402", median_gross_rent=850.0,
                                   renter_share=0.48, population=4800, density_tier="low"),
        "location": LocationEnrichment(walk_score=52),
    },
]


def main():
    bar = "=" * 80
    for s in SCENARIOS:
        print("\n" + bar)
        print(s["label"])
        print(bar)
        lead = s["lead"]
        score = score_lead(lead, s["company"], s["news"], s["market"], s["location"])
        enriched = EnrichedLead(
            lead=lead, company=s["company"], news=s["news"], market=s["market"],
            location=s["location"], score=score,
            insights="", email_subject="", email_body="",
        )
        enriched.insights = build_insights(enriched)
        subj, body = draft_email(lead, s["company"], s["news"], s["market"],
                                 s["location"], score, enriched.insights)

        print(f"\n  Final score: {score.final_score:.1f}/100 — {score.tier}")
        print(f"  Categories:  Fit={score.fit.average:.1f}  Value={score.value.average:.1f}  "
              f"Timing={score.timing.average:.1f}  Intent={score.intent.average:.1f}")
        print("\n  INSIGHTS BLOCK:")
        for ln in enriched.insights.splitlines():
            print(f"    {ln}")
        print(f"\n  EMAIL — Subject: {subj}")
        for ln in body.splitlines():
            print(f"    {ln}")


if __name__ == "__main__":
    main()
