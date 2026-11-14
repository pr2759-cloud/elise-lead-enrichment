"""Synthetic enriched rows with outcomes, for tests and for demoing `learn` and
`pipeline-report` before real outcome data exists.

THE DATA IS SYNTHETIC. Outcomes are drawn so that Timing drives conversion far
more than the hand-set weights assume. That lets the tests check that `learn`
recovers a known truth; it says nothing about what drives real conversions.

    python tests/synthetic.py data/synthetic_outcomes.csv
"""
from __future__ import annotations
import csv
import math
import random
import sys

SOURCES = [("website_demo_form", 1.0), ("webinar", 0.6), ("content_download", 0.0), ("paid_search", -0.6)]


def make_rows(n: int = 200, seed: int = 11):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        source, source_lift = rng.choice(SOURCES)
        fit, value, timing, intent = (round(rng.uniform(2, 10), 2) for _ in range(4))
        score = round(10 * (0.30 * fit + 0.25 * value + 0.25 * timing + 0.20 * intent), 1)
        tier = "HOT" if score >= 80 else "WARM" if score >= 60 else "COOL" if score >= 40 else "COLD"
        action = "send" if score >= 80 else "review" if score >= 60 else "silent"
        # True model: timing dominates, fit matters a little, value and intent barely.
        logit = -6.0 + 0.75 * timing + 0.15 * fit + 0.02 * value + 0.02 * intent + source_lift
        p = 1 / (1 + math.exp(-logit))
        outcome = "meeting" if rng.random() < p else "no_response"
        if rng.random() < 0.1:
            outcome = ""  # some leads still open: unknown outcome
        rows.append({
            "person_name": f"Lead {i}", "person_email": f"lead{i}@example{i % 37}.com",
            "company": f"Operator {i % 37}", "source": source, "campaign": f"{source}_q3",
            "score": score, "tier": tier, "action": action,
            "route": "nurture" if action == "silent" else "commercial_sdr",
            "fit_score": fit, "value_score": value, "timing_score": timing, "intent_score": intent,
            "outcome": outcome,
        })
    return rows


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "data/synthetic_outcomes.csv"
    rows = make_rows()
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {len(rows)} synthetic rows to {out}")
