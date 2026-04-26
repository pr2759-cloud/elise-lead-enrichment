"""Batch run report: aggregates per-lead results into a single summary.

Written to stdout at the end of every run, and can also be rendered as a
Markdown block for pasting into Slack/email.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from typing import List

from .models import EnrichedLead


@dataclass
class RunReport:
    total: int
    by_tier: Counter
    api_errors: Counter  # per-API error counts across the batch
    avg_score: float
    avg_signals_resolved: float
    top_n: List[EnrichedLead]  # top leads by score (for quick SDR review)
    run_duration_seconds: float

    def to_plain_text(self) -> str:
        lines = [
            "=" * 78,
            f"RUN SUMMARY — {self.total} leads processed in {self.run_duration_seconds:.1f}s",
            "=" * 78,
            f"  Average score: {self.avg_score:.1f}/100",
            f"  Average signals resolved: {self.avg_signals_resolved:.1f}/13",
            "",
            "  By tier:",
        ]
        for tier in ("HOT", "WARM", "COOL", "COLD"):
            count = self.by_tier.get(tier, 0)
            pct = (count / self.total * 100) if self.total else 0
            lines.append(f"    {tier:5s}  {count:3d}  ({pct:4.1f}%)")

        if self.api_errors:
            lines.append("")
            lines.append("  API errors:")
            for api, count in self.api_errors.most_common():
                lines.append(f"    {api:12s}  {count}")

        if self.top_n:
            lines.append("")
            lines.append(f"  Top {len(self.top_n)} leads:")
            for e in self.top_n:
                lines.append(
                    f"    {e.score.final_score:5.1f}  {e.score.tier:5s}  "
                    f"{e.lead.company:35.35s}  {e.lead.person_email}"
                )
        lines.append("=" * 78)
        return "\n".join(lines)

    def to_markdown(self) -> str:
        lines = [
            f"## Lead enrichment run summary",
            "",
            f"Processed **{self.total}** leads in {self.run_duration_seconds:.1f}s. "
            f"Average score {self.avg_score:.1f}/100.",
            "",
            "### By tier",
            "",
            "| Tier | Count | % |",
            "|---|---|---|",
        ]
        for tier in ("HOT", "WARM", "COOL", "COLD"):
            count = self.by_tier.get(tier, 0)
            pct = (count / self.total * 100) if self.total else 0
            lines.append(f"| {tier} | {count} | {pct:.1f}% |")

        if self.top_n:
            lines += [
                "",
                "### Top leads",
                "",
                "| Score | Tier | Company | Contact |",
                "|---|---|---|---|",
            ]
            for e in self.top_n:
                lines.append(
                    f"| {e.score.final_score:.1f} | {e.score.tier} | "
                    f"{e.lead.company} | {e.lead.person_email} |"
                )

        if self.api_errors:
            lines += ["", "### API error counts", ""]
            for api, count in self.api_errors.most_common():
                lines.append(f"- **{api}**: {count}")

        return "\n".join(lines)


def build_report(
    enriched: List[EnrichedLead], duration_seconds: float, top_n: int = 5,
) -> RunReport:
    tiers = Counter()
    api_errors = Counter()
    total_score = 0.0
    total_signals = 0.0

    for e in enriched:
        tiers[e.score.tier] += 1
        total_score += e.score.final_score
        resolved = e.score.total_signals_count - e.score.missing_signals_count
        total_signals += resolved
        for err in e.errors:
            # Errors are formatted as "service: details" — bucket by service
            bucket = err.split(":", 1)[0].strip()
            api_errors[bucket] += 1

    count = len(enriched)
    return RunReport(
        total=count,
        by_tier=tiers,
        api_errors=api_errors,
        avg_score=(total_score / count) if count else 0.0,
        avg_signals_resolved=(total_signals / count) if count else 0.0,
        top_n=sorted(enriched, key=lambda e: e.score.final_score, reverse=True)[:top_n],
        run_duration_seconds=duration_seconds,
    )
