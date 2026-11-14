"""Pipeline report (v2): where leads come from, what happened to them, and
whether the score predicts anything.

Works on flat rows — the enriched CSV, the Google Sheet, or the enriched JSON —
so sales can fill in the `outcome` column and re-run the report at any time.

Sections:
  By source / campaign  attribution: volume, quality and conversion per channel
  By tier               the scoring check: do HOT leads actually convert best?
  By action / route     what the gate and routing did with the pipeline
"""
from __future__ import annotations
import json
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from . import config

TIER_ORDER = ["HOT", "WARM", "COOL", "COLD"]


def outcome_label(value: str) -> Optional[int]:
    """1 = positive outcome, 0 = negative, None = not yet known / unrecognised."""
    v = (value or "").strip().lower()
    if v in config.POSITIVE_OUTCOMES:
        return 1
    if v in config.NEGATIVE_OUTCOMES:
        return 0
    return None


def _num(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@dataclass
class Group:
    leads: int = 0
    score_total: float = 0.0
    actions: Dict[str, int] = field(default_factory=lambda: {"send": 0, "review": 0, "silent": 0})
    labelled: int = 0
    positive: int = 0

    def add(self, row: dict) -> None:
        self.leads += 1
        self.score_total += _num(row.get("score"))
        a = (row.get("action") or "").strip()
        if a in self.actions:
            self.actions[a] += 1
        y = outcome_label(row.get("outcome", ""))
        if y is not None:
            self.labelled += 1
            self.positive += y

    @property
    def avg_score(self) -> float:
        return self.score_total / self.leads if self.leads else 0.0

    @property
    def conversion(self) -> Optional[float]:
        return self.positive / self.labelled if self.labelled else None


def _group_by(rows: Iterable[dict], key: str, order: Optional[List[str]] = None) -> "OrderedDict[str, Group]":
    groups: Dict[str, Group] = {}
    for r in rows:
        k = (r.get(key) or "").strip() or "(unknown)"
        groups.setdefault(k, Group()).add(r)
    if order:
        keys = [k for k in order if k in groups] + sorted(k for k in groups if k not in order)
    else:
        keys = sorted(groups, key=lambda k: -groups[k].leads)
    return OrderedDict((k, groups[k]) for k in keys)


@dataclass
class PipelineReport:
    total: int
    labelled: int
    positive: int
    by_source: "OrderedDict[str, Group]"
    by_campaign: "OrderedDict[str, Group]"
    by_tier: "OrderedDict[str, Group]"
    by_action: "OrderedDict[str, Group]"
    by_route: "OrderedDict[str, Group]"

    def scoring_check(self) -> str:
        """Plain-language verdict on whether conversion rises with tier."""
        rates = [(t, g.conversion) for t, g in self.by_tier.items()
                 if t in TIER_ORDER and g.labelled >= 5]
        if len(rates) < 2:
            return "Not enough labelled leads per tier yet (need 5+ in at least two tiers)."
        inversions = [
            f"{rates[i + 1][0]} ({rates[i + 1][1]:.0%}) converts above {rates[i][0]} ({rates[i][1]:.0%})"
            for i in range(len(rates) - 1) if rates[i + 1][1] > rates[i][1]
        ]
        if inversions:
            return "Scoring needs recalibration: " + "; ".join(inversions) + ". Run `learn`."
        return "Conversion falls with tier as expected; the score is ranking leads in the right order."

    # -- rendering --------------------------------------------------------
    @staticmethod
    def _table(title: str, groups: "OrderedDict[str, Group]") -> List[str]:
        lines = [f"  {title}", f"    {'':22s} {'leads':>5s} {'avg':>5s} {'send':>5s} {'review':>6s} "
                 f"{'silent':>6s} {'known':>5s} {'conv':>6s}"]
        for name, g in groups.items():
            conv = f"{g.conversion:.0%}" if g.conversion is not None else "–"
            lines.append(
                f"    {name[:22]:22s} {g.leads:5d} {g.avg_score:5.1f} {g.actions['send']:5d} "
                f"{g.actions['review']:6d} {g.actions['silent']:6d} {g.labelled:5d} {conv:>6s}"
            )
        return lines + [""]

    def to_plain_text(self) -> str:
        overall = f"{self.positive / self.labelled:.0%}" if self.labelled else "–"
        lines = [
            "=" * 78,
            f"PIPELINE REPORT — {self.total} leads, {self.labelled} with a known outcome, "
            f"overall conversion {overall}",
            "  (conv = positive outcomes / leads with a known outcome)",
            "=" * 78,
        ]
        lines += self._table("By source (attribution)", self.by_source)
        if len(self.by_campaign) > 1 or "(unknown)" not in self.by_campaign:
            lines += self._table("By campaign", self.by_campaign)
        lines += self._table("By tier (scoring check)", self.by_tier)
        lines.append(f"    → {self.scoring_check()}")
        lines.append("")
        lines += self._table("By action (gate)", self.by_action)
        lines += self._table("By route (owner)", self.by_route)
        lines.append("=" * 78)
        return "\n".join(lines)

    def to_markdown(self) -> str:
        def table(title: str, groups) -> List[str]:
            out = [f"### {title}", "", "| | Leads | Avg score | Send | Review | Silent | Known outcome | Conversion |",
                   "|---|---|---|---|---|---|---|---|"]
            for name, g in groups.items():
                conv = f"{g.conversion:.0%}" if g.conversion is not None else "–"
                out.append(f"| {name} | {g.leads} | {g.avg_score:.1f} | {g.actions['send']} | "
                           f"{g.actions['review']} | {g.actions['silent']} | {g.labelled} | {conv} |")
            return out + [""]
        lines = [f"## Pipeline report", "", f"{self.total} leads, {self.labelled} with a known outcome.", ""]
        lines += table("By source", self.by_source)
        lines += table("By tier", self.by_tier)
        lines += [f"**Scoring check:** {self.scoring_check()}", ""]
        lines += table("By action", self.by_action)
        lines += table("By route", self.by_route)
        return "\n".join(lines)


def build_pipeline_report(rows: List[dict]) -> PipelineReport:
    labels = [outcome_label(r.get("outcome", "")) for r in rows]
    known = [y for y in labels if y is not None]
    return PipelineReport(
        total=len(rows),
        labelled=len(known),
        positive=sum(known),
        by_source=_group_by(rows, "source"),
        by_campaign=_group_by(rows, "campaign"),
        by_tier=_group_by(rows, "tier", TIER_ORDER),
        by_action=_group_by(rows, "action", ["send", "review", "silent"]),
        by_route=_group_by(rows, "route"),
    )


# ---------------------------------------------------------------------------
# Loading rows from any of the three output formats
# ---------------------------------------------------------------------------
def _flatten_json_record(r: dict) -> dict:
    """Turn one record from the enriched JSON into the flat row shape."""
    lead = r.get("lead", {})
    s = r.get("score", {})
    d = r.get("decision", {})

    def avg(cat: str) -> float:
        subs = (s.get(cat) or {}).get("sub_signals") or {}
        return sum(subs.values()) / len(subs) if subs else 0.0

    row = dict(lead)
    row.update({
        "score": s.get("final", 0),
        "tier": s.get("tier", ""),
        "fit_score": avg("fit"), "value_score": avg("value"),
        "timing_score": avg("timing"), "intent_score": avg("intent"),
        "action": d.get("action", ""), "route": d.get("route", ""),
        "data_confidence": d.get("data_confidence", ""),
    })
    return row


def load_rows(path: str) -> List[dict]:
    """Load flat rows from an enriched .csv or .json file."""
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [_flatten_json_record(r) for r in data]
    from .csv_io import read_rows
    return read_rows(path)
