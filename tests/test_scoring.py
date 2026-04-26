"""Unit tests — exercise the pure-logic layers without hitting any API."""
import sys
from datetime import datetime
from pathlib import Path

# Ensure src/ is importable when running this file directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.heuristics.email import (
    email_quality_score, is_free_provider, seniority_score,
)
from src.heuristics.market_tiers import market_tier_score
from src.heuristics.seasonality import seasonality_score
from src.models import (
    CompanyEnrichment, Lead, LocationEnrichment, MarketEnrichment, NewsEnrichment,
)
from src.scoring.engine import score_lead


def test_free_provider_detection():
    assert is_free_provider("jane@gmail.com") is True
    assert is_free_provider("jane@acme.com") is False
    assert is_free_provider("") is False


def test_email_quality_scoring():
    assert email_quality_score("jane@greystar.com") == 10.0
    assert email_quality_score("jane@gmail.com") == 3.0
    assert email_quality_score("") == 0.0


def test_seniority_vp_keyword():
    assert seniority_score("Jane Doe, VP of Leasing", "jane@acme.com") == 10.0


def test_seniority_generic_alias_overrides():
    # info@ is a generic alias — even if name looks senior we score it down
    assert seniority_score("VP Something", "info@acme.com") == 3.0


def test_seniority_manager_keyword():
    assert seniority_score("Jane Doe, Leasing Manager", "jane@acme.com") == 7.0


def test_seniority_default():
    assert seniority_score("Jane Doe", "jane.doe@acme.com") == 5.0


def test_market_tier_t1():
    assert market_tier_score("New York", "NY", "US") == 10.0
    assert market_tier_score("san francisco", "CA", "US") == 10.0


def test_market_tier_t2():
    assert market_tier_score("Atlanta", "GA", "US") == 7.0


def test_market_tier_other_us():
    assert market_tier_score("Boise", "ID", "US") == 5.0


def test_market_tier_international():
    assert market_tier_score("London", "", "UK") == 4.0


def test_seasonality_peak():
    assert seasonality_score(datetime(2025, 6, 15)) == 10.0


def test_seasonality_shoulder():
    assert seasonality_score(datetime(2025, 3, 15)) == 7.0
    assert seasonality_score(datetime(2025, 10, 15)) == 7.0


def test_seasonality_off():
    assert seasonality_score(datetime(2025, 1, 15)) == 4.0
    assert seasonality_score(datetime(2025, 12, 15)) == 4.0


def test_end_to_end_scoring_hot_lead():
    """Scoring works end-to-end with synthetic enrichment data."""
    lead = Lead(
        person_name="Jane Doe",
        person_email="jane.doe@greystar.com",
        company="Greystar",
        property_address="312 Peachtree St 30308",
        city="Atlanta", state="GA", country="US",
    )
    company = CompanyEnrichment(
        has_wikipedia_page=True,
        matches_multifamily=True,
        multi_property_signals=True,
        wikipedia_title="Greystar Real Estate Partners",
    )
    news = NewsEnrichment(
        articles_30d=5, articles_90d=12,
        trigger_headline_30d="Greystar acquires 1200 units in Atlanta",
        has_tech_news=True,
    )
    market = MarketEnrichment(
        zip_code="30308",
        median_gross_rent=2040.0,
        renter_share=0.71,
        population=35000,
        density_tier="high",
    )
    location = LocationEnrichment(walk_score=88, transit_score=72, bike_score=65)

    score = score_lead(lead, company, news, market, location)
    assert score.final_score >= 85, f"Expected HOT but got {score.final_score}"
    assert score.tier == "HOT"


def test_end_to_end_scoring_cold_lead():
    """Low-quality lead scores cold."""
    lead = Lead(
        person_name="Tom Wilson",
        person_email="tom@gmail.com",
        company="Wilson Properties",
        property_address="500 Oak Ave 45402",
        city="Dayton", state="OH", country="US",
    )
    score = score_lead(
        lead,
        CompanyEnrichment(),  # no Wikipedia presence
        NewsEnrichment(articles_30d=0, articles_90d=0),
        MarketEnrichment(
            zip_code="45402", median_gross_rent=950.0,
            renter_share=0.45, population=5000, density_tier="low",
        ),
        LocationEnrichment(walk_score=55),
    )
    assert score.tier in {"COOL", "COLD"}, f"Expected COOL/COLD but got {score.tier}"


def test_partial_data_does_not_tank_score():
    """When every API fails, the score should be neutral — not zero."""
    lead = Lead(
        person_name="Jane Director", person_email="jane@goodcompany.com",
        company="GoodCompany", property_address="1 Main St 10001",
        city="New York", state="NY", country="US",
    )
    score = score_lead(
        lead,
        CompanyEnrichment(error="wiki down"),
        NewsEnrichment(error="news down"),
        MarketEnrichment(error="census down"),
        LocationEnrichment(error="walkscore down"),
    )
    # Should be ≥ 40 (COOL or better) because neutral fallbacks keep us above floor
    assert score.final_score >= 40


if __name__ == "__main__":
    import traceback
    failures = 0
    total = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            total += 1
            try:
                fn()
                print(f"PASS {name}")
            except Exception:
                failures += 1
                print(f"FAIL {name}")
                traceback.print_exc()
    print(f"\n{total - failures}/{total} passed")
    sys.exit(1 if failures else 0)
