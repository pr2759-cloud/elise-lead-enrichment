"""CSV input/output adapter. Used by --csv mode and for loading bundled samples."""
from __future__ import annotations
import csv
import logging
from typing import Iterable, List

from .models import EnrichedLead, INPUT_COLUMNS, Lead, OUTPUT_COLUMNS

log = logging.getLogger(__name__)


def read_leads(path: str) -> List[Lead]:
    leads: List[Lead] = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in INPUT_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")
        for row in reader:
            leads.append(Lead.from_row(row))
    return leads


def read_rows(path: str) -> List[dict]:
    """Read any CSV (e.g. an enriched output with outcomes filled in) as dicts."""
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_enriched(path: str, enriched: Iterable[EnrichedLead]) -> int:
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for e in enriched:
            writer.writerow(e.to_row())
            rows += 1
    log.info("Wrote %d enriched rows to %s", rows, path)
    return rows
