"""Tests for the HTTP client (retry logic) and report builder.

These are unit tests with no real network calls — we patch requests.get to
return controlled responses.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.http_client import HTTPError, get_json
from src.models import (
    CategoryScore, CompanyEnrichment, EnrichedLead, Lead, LeadScore,
    LocationEnrichment, MarketEnrichment, NewsEnrichment,
)
from src.report import build_report


def _mock_response(status_code=200, json_data=None, headers=None):
    m = MagicMock()
    m.status_code = status_code
    m.ok = 200 <= status_code < 300
    m.text = str(json_data or "")
    m.headers = headers or {}
    m.json.return_value = json_data if json_data is not None else {}
    return m


def test_http_client_succeeds_first_try():
    with patch("src.http_client.requests.get") as mock_get:
        mock_get.return_value = _mock_response(200, {"ok": True})
        result = get_json("https://example.com/api")
        assert result == {"ok": True}
        assert mock_get.call_count == 1


def test_http_client_retries_on_500():
    with patch("src.http_client.requests.get") as mock_get, \
         patch("src.http_client.time.sleep"):  # don't actually sleep
        mock_get.side_effect = [
            _mock_response(500),
            _mock_response(500),
            _mock_response(200, {"ok": True}),
        ]
        result = get_json("https://example.com/api", max_attempts=3)
        assert result == {"ok": True}
        assert mock_get.call_count == 3


def test_http_client_retries_on_429_and_respects_retry_after():
    with patch("src.http_client.requests.get") as mock_get, \
         patch("src.http_client.time.sleep") as mock_sleep:
        mock_get.side_effect = [
            _mock_response(429, headers={"Retry-After": "2"}),
            _mock_response(200, {"ok": True}),
        ]
        result = get_json("https://example.com/api", max_attempts=3)
        assert result == {"ok": True}
        assert mock_sleep.called


def test_http_client_gives_up_after_max_attempts():
    with patch("src.http_client.requests.get") as mock_get, \
         patch("src.http_client.time.sleep"):
        mock_get.return_value = _mock_response(500)
        try:
            get_json("https://example.com/api", max_attempts=3)
            assert False, "should have raised"
        except HTTPError:
            pass
        assert mock_get.call_count == 3


def test_http_client_no_retry_on_403():
    """403 is a permission problem; retrying won't help."""
    with patch("src.http_client.requests.get") as mock_get:
        mock_get.return_value = _mock_response(403)
        try:
            get_json("https://example.com/api", max_attempts=3)
            assert False, "should have raised"
        except HTTPError:
            pass
        assert mock_get.call_count == 1  # no retry


def test_http_client_accept_404():
    with patch("src.http_client.requests.get") as mock_get:
        mock_get.return_value = _mock_response(404)
        result = get_json("https://example.com/api", accept_404=True)
        assert result is None


def test_report_tier_distribution():
    """Report correctly aggregates tier counts across a batch."""
    results = []
    for score_val, tier in [(90, "HOT"), (75, "WARM"), (75, "WARM"), (50, "COOL"), (25, "COLD")]:
        lead = Lead("Test", "t@t.com", "Co", "1 St", "NYC", "NY", "US")
        ls = LeadScore(
            fit=CategoryScore("fit", 0.30, {"a": score_val / 10}),
            value=CategoryScore("value", 0.25, {"a": score_val / 10}),
            timing=CategoryScore("timing", 0.25, {"a": score_val / 10}),
            intent=CategoryScore("intent", 0.20, {"a": score_val / 10}),
        )
        e = EnrichedLead(
            lead=lead, company=CompanyEnrichment(), news=NewsEnrichment(),
            market=MarketEnrichment(), location=LocationEnrichment(), score=ls,
            insights="", email_subject="", email_body="",
        )
        results.append(e)
    report = build_report(results, duration_seconds=1.5)
    assert report.total == 5
    assert report.by_tier["HOT"] == 1
    assert report.by_tier["WARM"] == 2
    assert report.by_tier["COOL"] == 1
    assert report.by_tier["COLD"] == 1


def test_report_api_error_aggregation():
    """Per-API error counts are aggregated by service name prefix."""
    lead = Lead("T", "t@t.com", "Co", "1 St", "NYC", "NY", "US")
    ls = LeadScore(
        fit=CategoryScore("fit", 0.30, {"a": 5}),
        value=CategoryScore("value", 0.25, {"a": 5}),
        timing=CategoryScore("timing", 0.25, {"a": 5}),
        intent=CategoryScore("intent", 0.20, {"a": 5}),
    )
    e1 = EnrichedLead(
        lead=lead, company=CompanyEnrichment(), news=NewsEnrichment(),
        market=MarketEnrichment(), location=LocationEnrichment(), score=ls,
        insights="", email_subject="", email_body="",
        errors=["newsapi: rate limited", "census: fetch failed"],
    )
    e2 = EnrichedLead(
        lead=lead, company=CompanyEnrichment(), news=NewsEnrichment(),
        market=MarketEnrichment(), location=LocationEnrichment(), score=ls,
        insights="", email_subject="", email_body="",
        errors=["newsapi: rate limited"],
    )
    report = build_report([e1, e2], duration_seconds=2.0)
    assert report.api_errors["newsapi"] == 2
    assert report.api_errors["census"] == 1


def test_report_markdown_renders():
    """Markdown renderer produces something that parses as markdown (sanity check)."""
    lead = Lead("T", "t@t.com", "Co", "1 St", "NYC", "NY", "US")
    ls = LeadScore(
        fit=CategoryScore("fit", 0.30, {"a": 9}),
        value=CategoryScore("value", 0.25, {"a": 9}),
        timing=CategoryScore("timing", 0.25, {"a": 9}),
        intent=CategoryScore("intent", 0.20, {"a": 9}),
    )
    e = EnrichedLead(
        lead=lead, company=CompanyEnrichment(), news=NewsEnrichment(),
        market=MarketEnrichment(), location=LocationEnrichment(), score=ls,
        insights="", email_subject="", email_body="",
    )
    report = build_report([e], duration_seconds=1.0)
    md = report.to_markdown()
    assert "## Lead enrichment run summary" in md
    assert "| Tier |" in md


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
