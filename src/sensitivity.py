"""Sensitivity analysis tool.

Reads already-enriched results (JSON) and re-scores them under different weight
schemes, so the sales team can see how their rankings would change before
committing to a weight change.

Usage:
    python -m src.sensitivity enriched.json \\
        --weights fit=0.40 value=0.25 timing=0.20 intent=0.15

Or to compare multiple schemes side-by-side:
    python -m src.sensitivity enriched.json --compare
"""
from __future__ import annotations
import argparse
import json
import sys
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class LeadRow:
    company: str
    email: str
    fit: float
    value: float
    timing: float
    intent: float

    def score(self, weights: Dict[str, float]) -> float:
        return round(
            10 * (
                weights["fit"] * self.fit
                + weights["value"] * self.value
                + weights["timing"] * self.timing
                + weights["intent"] * self.intent
            ),
            1,
        )


def _tier(score: float) -> str:
    if score >= 80: return "HOT"
    if score >= 60: return "WARM"
    if score >= 40: return "COOL"
    return "COLD"


def load_rows(json_path: str) -> List[LeadRow]:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    rows: List[LeadRow] = []
    for r in data:
        lead = r.get("lead", {})
        s = r.get("score", {})
        rows.append(LeadRow(
            company=lead.get("company", ""),
            email=lead.get("person_email", ""),
            fit=_avg(s.get("fit", {}).get("sub_signals", {})),
            value=_avg(s.get("value", {}).get("sub_signals", {})),
            timing=_avg(s.get("timing", {}).get("sub_signals", {})),
            intent=_avg(s.get("intent", {}).get("sub_signals", {})),
        ))
    return rows


def _avg(sub_signals: Dict[str, float]) -> float:
    if not sub_signals:
        return 0.0
    return sum(sub_signals.values()) / len(sub_signals)


def parse_weights(items: List[str]) -> Dict[str, float]:
    weights = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Weight spec must be key=value, got {item!r}")
        k, v = item.split("=", 1)
        weights[k.strip()] = float(v)
    missing = {"fit", "value", "timing", "intent"} - set(weights)
    if missing:
        raise ValueError(f"Missing weights: {missing}")
    total = sum(weights.values())
    if abs(total - 1.0) > 0.01:
        raise ValueError(f"Weights must sum to 1.0, got {total:.3f}")
    return weights


PRESET_SCHEMES = {
    "current":        {"fit": 0.30, "value": 0.25, "timing": 0.25, "intent": 0.20},
    "chatgpt":        {"fit": 0.30, "value": 0.30, "timing": 0.15, "intent": 0.25},
    "fit_heavy":      {"fit": 0.50, "value": 0.20, "timing": 0.20, "intent": 0.10},
    "timing_heavy":   {"fit": 0.20, "value": 0.20, "timing": 0.45, "intent": 0.15},
    "value_heavy":    {"fit": 0.20, "value": 0.45, "timing": 0.20, "intent": 0.15},
}


def cmd_rescore(args):
    rows = load_rows(args.input)
    weights = parse_weights(args.weights)
    print(f"Re-scoring {len(rows)} leads with weights: {weights}")
    print()
    print(f"{'Score':>6s} {'Tier':5s}  {'Company':40s} {'Contact'}")
    print("-" * 90)
    rescored = sorted(rows, key=lambda r: r.score(weights), reverse=True)
    for r in rescored:
        s = r.score(weights)
        print(f"{s:6.1f} {_tier(s):5s}  {r.company[:40]:40s} {r.email}")
    return 0


def cmd_compare(args):
    rows = load_rows(args.input)
    schemes = PRESET_SCHEMES
    header = f"{'Company':30s} {'Contact':35s}  " + "  ".join(f"{k[:11]:>11s}" for k in schemes)
    print(header)
    print("-" * len(header))
    # Rank each lead under the "current" scheme for default sort order
    sort_scheme = schemes["current"]
    rows.sort(key=lambda r: r.score(sort_scheme), reverse=True)
    for r in rows:
        scores_str = "  ".join(
            f"{r.score(w):>6.1f} {_tier(r.score(w)):>4s}" for w in schemes.values()
        )
        print(f"{r.company[:30]:30s} {r.email[:35]:35s}  {scores_str}")
    print()
    print("Schemes:")
    for name, w in schemes.items():
        print(f"  {name:13s}  {w}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="sensitivity",
        description="Re-score enriched leads under alternative weighting schemes.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rescore = sub.add_parser("rescore", help="Re-score with a specific weight set")
    p_rescore.add_argument("input", help="Path to an enriched JSON produced by 'main.py ... --json'")
    p_rescore.add_argument("--weights", nargs="+", required=True,
                           help="Weight assignments e.g. fit=0.4 value=0.25 timing=0.2 intent=0.15")
    p_rescore.set_defaults(func=cmd_rescore)

    p_compare = sub.add_parser("compare", help="Compare all preset schemes side-by-side")
    p_compare.add_argument("input", help="Path to an enriched JSON produced by 'main.py ... --json'")
    p_compare.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
