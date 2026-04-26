"""Integration tests — hit real public APIs.

Skipped unless the RUN_INTEGRATION env var is set. Run with:
    RUN_INTEGRATION=1 python tests/test_integration.py

Only uses free APIs that don't need a key (Wikipedia, Census, Nominatim).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SKIP = not os.getenv("RUN_INTEGRATION")


def test_wikipedia_enrichment_real():
    if SKIP:
        print("SKIP test_wikipedia_enrichment_real (set RUN_INTEGRATION=1 to run)")
        return
    from src.enrich.wikipedia import enrich_company_wikipedia
    from src.cache import get_cache
    get_cache().clear("wikipedia")
    result = enrich_company_wikipedia("Greystar")
    assert result.error is None, f"unexpected error: {result.error}"
    assert result.has_wikipedia_page, "Greystar should have a Wikipedia page"
    assert result.wikipedia_url, "should have a URL"
    assert result.wikipedia_summary, "should have a summary"


def test_wikipedia_no_match():
    if SKIP:
        print("SKIP test_wikipedia_no_match")
        return
    from src.enrich.wikipedia import enrich_company_wikipedia
    from src.cache import get_cache
    get_cache().clear("wikipedia")
    result = enrich_company_wikipedia("ZZZ_NonexistentCompany_XYZ_12345")
    assert result.has_wikipedia_page is False
    assert result.parent_mention_only is False


def test_census_enrichment_real():
    if SKIP:
        print("SKIP test_census_enrichment_real")
        return
    from src.enrich.census import enrich_market
    from src.cache import get_cache
    get_cache().clear("census")
    # 10001 is NYC Chelsea/Midtown — definitely high renter share
    result = enrich_market("350 5th Ave, New York, NY 10001")
    assert result.error is None, f"unexpected error: {result.error}"
    assert result.zip_code == "10001"
    assert result.median_gross_rent is not None
    assert result.median_gross_rent > 1000, "NYC median rent should be > $1000"
    assert result.renter_share is not None
    assert result.renter_share > 0.5, "NYC 10001 should be >50% renter-occupied"


def test_end_to_end_pipeline_no_keys():
    """Full pipeline against real Wikipedia + Census only (no keys needed)."""
    if SKIP:
        print("SKIP test_end_to_end_pipeline_no_keys")
        return
    from src.pipeline import enrich_one
    from src.models import Lead
    from src.cache import get_cache
    get_cache().clear()

    lead = Lead(
        person_name="Jane Doe, VP of Leasing",
        person_email="jane@greystar.com",
        company="Greystar",
        property_address="350 5th Ave 10001",
        city="New York", state="NY", country="US",
    )
    result = enrich_one(lead)

    # Even without NewsAPI/WalkScore keys, Wikipedia + Census should produce
    # a meaningful score for a known multifamily operator in NYC.
    assert result.score.final_score >= 60, (
        f"Expected WARM or better for Greystar+NYC; got {result.score.final_score}"
    )
    print(f"   End-to-end real-API score: {result.score.final_score} [{result.score.tier}]")


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
