"""v2 tests: action gate, routing, unknown-data handling, attribution report,
and the learning loop. No network."""
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import config
from src.gating import decide
from src.learning import auc, coefficients_to_weights, learn, write_weights
from src.models import (
    CompanyEnrichment, Lead, LocationEnrichment, MarketEnrichment, NewsEnrichment,
)
from src.pipeline_report import build_pipeline_report, outcome_label
from src.routing import RouteContext, route_lead
from src.scoring.engine import score_lead
from synthetic import make_rows


def _lead(email="jane.doe@greystar.com", **kw):
    base = dict(person_name="Jane Doe, VP of Leasing", person_email=email, company="Greystar",
                property_address="312 Peachtree St NE 30308", city="Atlanta", state="GA", country="US")
    base.update(kw)
    return Lead(**base)


def _hot_inputs():
    company = CompanyEnrichment(has_wikipedia_page=True, matches_multifamily=True, multi_property_signals=True)
    news = NewsEnrichment(articles_30d=5, articles_90d=12,
                          trigger_headline_30d="Greystar acquires 1200 units", has_tech_news=True)
    market = MarketEnrichment(zip_code="30308", median_gross_rent=2040.0, renter_share=0.71,
                              population=35000, density_tier="high")
    location = LocationEnrichment(walk_score=88)
    return company, news, market, location


def _cold_inputs():
    return (CompanyEnrichment(), NewsEnrichment(),
            MarketEnrichment(zip_code="45402", median_gross_rent=850.0, renter_share=0.40,
                             population=4800, density_tier="low"),
            LocationEnrichment(walk_score=30))


# --- gate ------------------------------------------------------------------
def test_gate_sends_strong_well_evidenced_lead():
    lead = _lead()
    d = decide(lead, score_lead(lead, *_hot_inputs()))
    assert d.action == "send", d


def test_gate_reviews_strong_lead_with_personal_email():
    lead = _lead(email="jane.doe@gmail.com")
    s = score_lead(lead, *_hot_inputs())
    if s.final_score >= config.SEND_MIN_SCORE:
        assert decide(lead, s).action == "review"


def test_gate_silences_cold_lead():
    lead = _lead(person_name="Tom Wilson", email="tom@gmail.com", company="Wilson Properties",
                 city="Dayton", state="OH")
    d = decide(lead, score_lead(lead, *_cold_inputs()))
    assert d.action == "silent", d


def test_gate_reviews_when_data_is_mostly_missing():
    lead = _lead()
    s = score_lead(lead, CompanyEnrichment(error="x"), NewsEnrichment(error="x"),
                   MarketEnrichment(error="x"), LocationEnrichment(error="x"))
    assert s.data_confidence < config.MIN_DATA_CONFIDENCE
    d = decide(lead, s)
    assert d.action == "review" and "signals resolved" in d.reason


# --- unknown data ------------------------------------------------------------
def test_no_wikipedia_page_is_unknown_scale_not_small():
    lead = _lead()
    s = score_lead(lead, CompanyEnrichment(), *_hot_inputs()[1:])
    assert "company_scale" in s.fit.missing
    assert s.fit.sub_signals["company_scale"] == config.NEUTRAL_SUBSIGNAL_SCORE


# --- routing -----------------------------------------------------------------
def test_routing_multi_property_goes_to_enterprise():
    lead = _lead()
    company, news, market, location = _hot_inputs()
    s = score_lead(lead, company, news, market, location)
    r = route_lead(RouteContext(lead, s, company, news, "send"))
    assert r.route == "enterprise_ae", r


def test_routing_first_match_wins_and_custom_rules_work():
    lead = _lead()
    company, news, market, location = _hot_inputs()
    s = score_lead(lead, company, news, market, location)
    rules = [{"route": "a", "when": {"tier_in": ["COLD"]}},
             {"route": "b", "when": {"has_trigger_30d": True}},
             {"route": "c", "when": {}}]
    assert route_lead(RouteContext(lead, s, company, news, "send"), rules).route == "b"


def test_routing_silent_goes_to_nurture():
    lead = _lead(email="tom@gmail.com")
    company, news, market, location = _cold_inputs()
    s = score_lead(lead, company, news, market, location)
    r = route_lead(RouteContext(lead, s, company, news, "silent"))
    assert r.route == "nurture", r


# --- pipeline integration ----------------------------------------------------
def test_pipeline_drafts_nothing_for_silent_leads():
    from src import pipeline
    company, news, market, location = _cold_inputs()
    with patch.object(pipeline, "enrich_company_wikipedia", return_value=company), \
         patch.object(pipeline, "enrich_news", return_value=news), \
         patch.object(pipeline, "enrich_market", return_value=market), \
         patch.object(pipeline, "enrich_location", return_value=location), \
         patch.object(pipeline, "draft_email") as drafter:
        e = pipeline.enrich_one(_lead(email="tom@gmail.com", source="webinar"))
    assert e.action == "silent"
    assert e.email_body == "" and not drafter.called
    row = e.to_row()
    assert row["action"] == "silent" and row["route"] == "nurture" and row["source"] == "webinar"


def test_lead_from_row_reads_optional_columns():
    lead = Lead.from_row({"person_email": "a@b.com", "company": "B", "source": " webinar ",
                          "outcome": "Meeting"})
    assert lead.source == "webinar" and lead.outcome == "meeting" and lead.country == "US"


# --- pipeline report ---------------------------------------------------------
def test_outcome_labels():
    assert outcome_label("Meeting") == 1
    assert outcome_label("no_response") == 0
    assert outcome_label("") is None and outcome_label("maybe") is None


def test_pipeline_report_groups_by_source_and_flags_inverted_tiers():
    rows = (
        [{"source": "webinar", "tier": "HOT", "score": 85, "action": "send", "outcome": "no_response"}] * 6
        + [{"source": "webinar", "tier": "WARM", "score": 65, "action": "review", "outcome": "meeting"}] * 6
        + [{"source": "paid", "tier": "COLD", "score": 20, "action": "silent", "outcome": ""}] * 3
    )
    rep = build_pipeline_report(rows)
    assert rep.total == 15 and rep.labelled == 12 and rep.positive == 6
    assert rep.by_source["webinar"].leads == 12 and rep.by_source["webinar"].conversion == 0.5
    assert rep.by_source["paid"].conversion is None
    assert "recalibration" in rep.scoring_check()
    assert "PIPELINE REPORT" in rep.to_plain_text() and "| webinar |" in rep.to_markdown()


# --- learning loop -----------------------------------------------------------
def test_auc_basics():
    assert auc([3, 2, 1], [1, 0, 0]) == 1.0
    assert auc([1, 2, 3], [1, 0, 0]) == 0.0
    assert auc([1, 1], [1, 0]) == 0.5


def test_coefficients_to_weights_floors_and_normalises():
    w = coefficients_to_weights([1.0, -0.5, 3.0, 0.0])
    assert abs(sum(w.values()) - 1.0) < 0.01
    assert w["timing"] == max(w.values())
    assert min(w.values()) >= 0.05 - 1e-9, w   # the floor holds after normalising
    assert coefficients_to_weights([-1, -1, 0, 0]) is None


def test_learn_refuses_with_too_few_labels():
    r = learn(make_rows(n=20))
    assert r.learned_weights is None and not r.recommend and "at least" in r.message


def test_learn_recovers_known_driver_and_recommends():
    r = learn(make_rows(n=300))
    assert r.learned_weights is not None
    assert max(r.learned_weights, key=r.learned_weights.get) == "timing", r.learned_weights
    assert r.cv_auc > r.current_auc and r.recommend, r.to_plain_text()


def test_learned_weights_roundtrip_through_config():
    r = learn(make_rows(n=300))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "w.json")
        write_weights(r, path)
        with open(path) as f:
            saved = json.load(f)
        assert saved["weights"] == r.learned_weights and saved["n_labels"] == r.n_labels
        original = dict(config.CATEGORY_WEIGHTS)
        try:
            with patch.object(config, "LEARNED_WEIGHTS_PATH", path):
                config._load_learned_weights()
            assert config.CATEGORY_WEIGHTS == r.learned_weights
            assert config.WEIGHTS_SOURCE.startswith("learned")
        finally:
            config.CATEGORY_WEIGHTS.clear()
            config.CATEGORY_WEIGHTS.update(original)
            config.WEIGHTS_SOURCE = "default (hand-set)"


if __name__ == "__main__":
    import traceback
    fails = 0
    tests = [(n, f) for n, f in list(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails}/{len(tests)} passed")
    sys.exit(1 if fails else 0)
