"""JSON input/output adapter.

Useful when the tool is wired into other pipelines (CRM webhook, Zapier, etc.)
that prefer JSON over CSV.
"""
from __future__ import annotations
import json
import logging
from dataclasses import asdict
from typing import Iterable, List

from .models import EnrichedLead, Lead

log = logging.getLogger(__name__)


def read_leads(path: str) -> List[Lead]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"JSON input must be a list of lead objects; got {type(data).__name__}")
    leads: List[Lead] = []
    for i, row in enumerate(data):
        try:
            leads.append(Lead.from_row(row))
        except Exception as e:
            raise ValueError(f"Invalid lead at index {i}: {e}") from e
    return leads


def write_enriched(path: str, enriched: Iterable[EnrichedLead]) -> int:
    out = []
    count = 0
    for e in enriched:
        # Use asdict to get a full nested serialization, then flatten the
        # insight/email/score fields for convenience.
        record = {
            "lead": asdict(e.lead),
            "score": {
                "final": e.score.final_score,
                "tier": e.score.tier,
                "fit": asdict(e.score.fit),
                "value": asdict(e.score.value),
                "timing": asdict(e.score.timing),
                "intent": asdict(e.score.intent),
                "missing_signals": e.score.missing_signals_count,
                "total_signals": e.score.total_signals_count,
            },
            "enrichment": {
                "company": asdict(e.company),
                "news": asdict(e.news),
                "market": asdict(e.market),
                "location": asdict(e.location),
            },
            "outreach": {
                "subject": e.email_subject,
                "body": e.email_body,
            },
            "decision": {
                "action": e.action,
                "action_reason": e.action_reason,
                "route": e.route,
                "route_reason": e.route_reason,
                "data_confidence": round(e.score.data_confidence, 2),
            },
            "insights": e.insights,
            "errors": e.errors,
            "processed_at": e.processed_at,
        }
        out.append(record)
        count += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    log.info("Wrote %d records to %s", count, path)
    return count
