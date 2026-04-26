"""Main CLI entrypoint.

Modes:
  demo         Run on bundled sample leads and print results (no APIs or sheets needed)
  csv IN OUT   Read from CSV, write enriched CSV
  json IN OUT  Read from JSON, write enriched JSON
  sheet        Read/write via Google Sheets (uses env vars)
  reset-sheet  Reset sheet rows with given statuses back to 'pending'
  report IN    Render a run-summary report from an enriched JSON file
"""
from __future__ import annotations
import argparse
import json as _json
import logging
import sys
import time
from collections import Counter
from pathlib import Path
from typing import List

from . import config
from .csv_io import read_leads as read_csv, write_enriched as write_csv
from .json_io import read_leads as read_json, write_enriched as write_json
from .models import EnrichedLead, Lead
from .pipeline import enrich_one
from .report import build_report

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample_leads.csv"


def _setup_logging():
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )


def _banner():
    flags = config.runtime_flags()
    bits = [
        f"NewsAPI={'yes' if flags.have_newsapi else 'NO'}",
        f"WalkScore={'yes' if flags.have_walkscore else 'NO'}",
        f"Census={'yes' if flags.have_census else 'NO'}",
        f"LLMpolish={'yes' if flags.use_llm_polish else 'no'}",
    ]
    print(f"[EliseAI lead enrichment] runtime: {' | '.join(bits)}", flush=True)


def _print_enriched(e: EnrichedLead, verbose: bool = True) -> None:
    line = "=" * 78
    print(line)
    print(f"{e.lead.person_name} <{e.lead.person_email}> — {e.lead.company}")
    print(f"{e.lead.property_address}, {e.lead.city} {e.lead.state}")
    print(line)
    print(f"  SCORE: {e.score.final_score:.1f}  [{e.score.tier}]")
    if verbose:
        for name, cs in (("Fit", e.score.fit), ("Value", e.score.value),
                         ("Timing", e.score.timing), ("Intent", e.score.intent)):
            sig_str = ", ".join(f"{k}={v:.0f}" for k, v in cs.sub_signals.items())
            print(f"    {name:6s} {cs.average:.2f}/10  ({sig_str})")
        print()
        print("  INSIGHTS:")
        for ln in e.insights.splitlines():
            print(f"    {ln}")
        print()
        print(f"  EMAIL DRAFT — Subject: {e.email_subject}")
        for ln in e.email_body.splitlines():
            print(f"    {ln}")
        if e.errors:
            print()
            print(f"  NOTES: {'; '.join(e.errors)}")
    print()


def run_batch(leads: List[Lead]) -> List[EnrichedLead]:
    results: List[EnrichedLead] = []
    for lead in leads:
        try:
            results.append(enrich_one(lead))
        except Exception as e:
            logging.exception("pipeline failed for %s: %s", lead.company, e)
    return results


def cmd_demo(args) -> int:
    leads = read_csv(str(SAMPLE_CSV))
    print(f"Loaded {len(leads)} sample leads from {SAMPLE_CSV}")
    t0 = time.time()
    results = run_batch(leads)
    duration = time.time() - t0
    for r in sorted(results, key=lambda r: r.score.final_score, reverse=True):
        _print_enriched(r)
    if args.out:
        write_csv(args.out, results)
        print(f"Wrote {len(results)} rows to {args.out}")
    if args.json_out:
        write_json(args.json_out, results)
        print(f"Wrote {len(results)} records to {args.json_out}")
    report = build_report(results, duration)
    print(report.to_plain_text())
    return 0


def cmd_csv(args) -> int:
    leads = read_csv(args.input)
    print(f"Loaded {len(leads)} leads from {args.input}")
    if args.dry_run:
        print("DRY RUN — no enrichment will be performed. Leads parsed:")
        for l in leads:
            print(f"  {l.company} / {l.person_email} / {l.property_address}")
        return 0
    t0 = time.time()
    results = run_batch(leads)
    duration = time.time() - t0
    write_csv(args.output, results)
    print(f"Wrote {len(results)} enriched rows to {args.output}")
    report = build_report(results, duration)
    print(report.to_plain_text())
    return 0


def cmd_json(args) -> int:
    leads = read_json(args.input)
    print(f"Loaded {len(leads)} leads from {args.input}")
    if args.dry_run:
        print("DRY RUN — no enrichment will be performed.")
        return 0
    t0 = time.time()
    results = run_batch(leads)
    duration = time.time() - t0
    write_json(args.output, results)
    print(f"Wrote {len(results)} records to {args.output}")
    report = build_report(results, duration)
    print(report.to_plain_text())
    return 0


def cmd_sheet(args) -> int:
    from .sheets import (
        _open_sheet, ensure_header, read_pending_leads,
        write_enriched, mark_status,
    )
    ws = _open_sheet()
    ensure_header(ws)
    todo = read_pending_leads(ws)
    print(f"Sheet has {len(todo)} pending leads")
    if args.dry_run:
        for _, lead in todo:
            print(f"  DRY: {lead.company} / {lead.person_email}")
        return 0
    t0 = time.time()
    results: List[EnrichedLead] = []
    for row_num, lead in todo:
        mark_status(ws, row_num, "enriching")
        try:
            enriched = enrich_one(lead)
            write_enriched(ws, row_num, enriched)
            results.append(enriched)
        except Exception as exc:
            logging.exception("pipeline failed for row %d: %s", row_num, exc)
            mark_status(ws, row_num, "error", str(exc)[:500])
    duration = time.time() - t0
    report = build_report(results, duration)
    print(report.to_plain_text())
    return 0


def cmd_reset_sheet(args) -> int:
    from .sheets import _open_sheet, ensure_header
    ws = _open_sheet()
    ensure_header(ws)
    header = ws.row_values(1)
    if "status" not in header:
        print("Sheet has no 'status' column; nothing to reset.")
        return 0
    status_col = header.index("status") + 1
    all_values = ws.get_all_values()
    if len(all_values) <= 1:
        print("Sheet has no data rows.")
        return 0
    targets = []
    filter_all = args.only == ["all"]
    filters = {s.lower() for s in (args.only or [])}
    for i, row in enumerate(all_values[1:], start=2):
        current = row[status_col - 1] if len(row) >= status_col else ""
        if not filter_all and current.lower() not in filters:
            continue
        targets.append((i, current))
    if not targets:
        print("No rows match the filter.")
        return 0
    print(f"Resetting {len(targets)} rows...")
    for row_num, _ in targets:
        ws.update_cell(row_num, status_col, "pending")
    print("Done.")
    return 0


def cmd_report(args) -> int:
    with open(args.input, encoding="utf-8") as f:
        data = _json.load(f)

    tiers = Counter()
    api_errors = Counter()
    total_score = 0.0
    total_signals = 0.0
    top_rows = []

    for r in data:
        score_blk = r.get("score", {})
        tier = score_blk.get("tier", "?")
        final = float(score_blk.get("final", 0))
        tiers[tier] += 1
        total_score += final
        total_signals += float(score_blk.get("total_signals", 0)) - float(score_blk.get("missing_signals", 0))
        for err in r.get("errors", []):
            api_errors[err.split(":", 1)[0].strip()] += 1
        top_rows.append((final, tier, r.get("lead", {}).get("company", ""),
                         r.get("lead", {}).get("person_email", "")))

    total = len(data)
    print("=" * 78)
    print(f"REPORT — {total} leads")
    print("=" * 78)
    if total:
        print(f"  Average score: {total_score / total:.1f}/100")
        print(f"  Average signals resolved: {total_signals / total:.1f}/13")
    print("")
    print("  By tier:")
    for tier in ("HOT", "WARM", "COOL", "COLD"):
        c = tiers.get(tier, 0)
        pct = (c / total * 100) if total else 0
        print(f"    {tier:5s}  {c:3d}  ({pct:4.1f}%)")
    if api_errors:
        print("")
        print("  API errors:")
        for api, c in api_errors.most_common():
            print(f"    {api:12s}  {c}")
    print("")
    print("  Top 10:")
    for score, tier, company, email in sorted(top_rows, reverse=True)[:10]:
        print(f"    {score:5.1f}  {tier:5s}  {company[:35]:35s}  {email}")
    print("=" * 78)
    return 0


def main(argv=None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(
        prog="elise-lead-enrichment",
        description="Automated inbound lead enrichment for EliseAI SDRs.",
    )
    sub = parser.add_subparsers(dest="mode", required=True)

    p_demo = sub.add_parser("demo", help="Run on bundled sample leads (no sheet needed)")
    p_demo.add_argument("--out", help="Optional CSV path to also write results to")
    p_demo.add_argument("--json-out", dest="json_out", help="Optional JSON path to also write results to")
    p_demo.set_defaults(func=cmd_demo)

    p_csv = sub.add_parser("csv", help="Enrich leads from a CSV and write to another CSV")
    p_csv.add_argument("input", help="Input CSV path")
    p_csv.add_argument("output", help="Output CSV path")
    p_csv.add_argument("--dry-run", action="store_true", help="Parse inputs and exit without enriching")
    p_csv.set_defaults(func=cmd_csv)

    p_json = sub.add_parser("json", help="Enrich leads from JSON and write JSON output")
    p_json.add_argument("input", help="Input JSON path")
    p_json.add_argument("output", help="Output JSON path")
    p_json.add_argument("--dry-run", action="store_true", help="Parse inputs and exit without enriching")
    p_json.set_defaults(func=cmd_json)

    p_sheet = sub.add_parser("sheet", help="Enrich pending leads in the configured Google Sheet")
    p_sheet.add_argument("--dry-run", action="store_true", help="List pending leads without enriching")
    p_sheet.set_defaults(func=cmd_sheet)

    p_reset = sub.add_parser("reset-sheet", help="Reset rows in the sheet back to 'pending'")
    p_reset.add_argument("--only", nargs="+", default=["error"],
                         help="Statuses to reset (default: error only). Use 'all' for every row.")
    p_reset.set_defaults(func=cmd_reset_sheet)

    p_report = sub.add_parser("report", help="Render a summary report from an enriched JSON file")
    p_report.add_argument("input", help="Enriched JSON path")
    p_report.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    _banner()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
