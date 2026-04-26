"""Intent category: email quality, digital activity. (v1 — 2 of 5 signals.)

Deferred to v2 (would require APIs outside the free suggested set):
  - Hiring signals (Indeed / LinkedIn Jobs API)
  - Tech stack detection (BuiltWith / web scraping)
  - Operational pain from reviews (Google Places / Yelp)
"""
from __future__ import annotations

from ..config import CATEGORY_WEIGHTS, NEUTRAL_SUBSIGNAL_SCORE
from ..models import CategoryScore, CompanyEnrichment, Lead, NewsEnrichment
from ..heuristics.email import email_quality_score


def _digital_activity_score(company: CompanyEnrichment, news: NewsEnrichment) -> float:
    if news.error is None and news.has_tech_news:
        return 10.0
    if news.error is None and news.articles_90d > 0:
        return 6.0
    if company.error is None and company.has_wikipedia_page:
        return 4.0
    return 2.0


def score_intent(
    lead: Lead, company: CompanyEnrichment, news: NewsEnrichment
) -> CategoryScore:
    cat = CategoryScore(name="intent", weight=CATEGORY_WEIGHTS["intent"])

    # Email Quality (always computable locally)
    cat.sub_signals["email_quality"] = email_quality_score(lead.person_email)

    # Digital Activity (degrades gracefully if news is missing)
    if news.error is not None and company.error is not None:
        cat.sub_signals["digital_activity"] = NEUTRAL_SUBSIGNAL_SCORE
        cat.missing.append("digital_activity")
    else:
        cat.sub_signals["digital_activity"] = _digital_activity_score(company, news)

    return cat
