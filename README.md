# EliseAI Automated Inbound Lead Enrichment

Takes raw inbound leads (name, email, company, property address) and produces a **lead score**, a **personalized outreach email**, and a **sales insights block** — fully automated, using four free public APIs.

## What it does

For every inbound lead, the tool:

1. **Enriches** the lead by calling four public APIs:
   - **Wikipedia** — company notability, industry signals, portfolio-scale cues
   - **NewsAPI** — recent company news, trigger events, tech-adoption signals
   - **US Census ACS** — ZIP-level median rent, renter share, density
   - **WalkScore** — walkability, transit, and bike scores for the property
2. **Scores** the lead on a 0–100 scale using a four-category rubric (Fit / Value / Timing / Intent) with explicit sub-signals.
3. **Drafts** a personalized outreach email from one of five templates chosen by the dominant scoring category. With an Anthropic API key, the draft is polished by Claude Haiku. Without one, pure templates are used.
4. **Generates** a compact sales insights block organized around the four categories with concrete talking points.
5. **Writes** everything back to a Google Sheet (or CSV/JSON) and tags the row as `done`.
6. **Summarizes** every batch run with a tier breakdown, API error counts, and the top leads.

The pipeline runs automatically on a **daily schedule at 9am ET** via GitHub Actions, and can also be **manually triggered** from the Actions tab.

## Quickstart (no setup required)

Run against the bundled sample leads without any API keys. It uses Wikipedia and Census (both free, no key needed) and skips the rest gracefully:

```bash
pip install -r requirements.txt
python -m src.main demo
```

You'll see ten sample leads enriched and ranked, with a run-summary report at the end. Add `--out sample.csv` and/or `--json-out sample.json` to save results.

## Commands

| Command | What it does |
|---|---|
| `python -m src.main demo` | Run on bundled sample data, print ranked results + summary |
| `python -m src.main csv input.csv output.csv` | Batch-enrich a CSV file |
| `python -m src.main json input.json output.json` | Batch-enrich a JSON file |
| `python -m src.main sheet` | Production mode — read/write Google Sheets |
| `python -m src.main reset-sheet` | Reset sheet rows to `pending` for re-processing |
| `python -m src.main report input.json` | Print a run-summary report from an enriched JSON |
| `python -m src.sensitivity compare enriched.json` | Compare scores under preset weight schemes |
| `python -m src.sensitivity rescore enriched.json --weights fit=0.4 ...` | Re-score with custom weights |

Any enrichment command supports `--dry-run` to parse inputs without calling APIs.

## Configuration

Copy `.env.example` to `.env` and fill in the keys you have. All keys are optional — the tool degrades gracefully when any is missing. Missing sub-signals receive a neutral 5/10 rather than zero.

```bash
cp .env.example .env
# Edit .env with your keys
```

### API keys (all free)

| Service | Where to get a key | Free tier |
|---|---|---|
| NewsAPI | https://newsapi.org/register | 100 requests/day |
| WalkScore | https://www.walkscore.com/professional/api-sign-up.php | 5,000 calls/day |
| US Census | https://api.census.gov/data/key_signup.html | Optional; works without for light use |
| Anthropic (optional) | https://console.anthropic.com | Polishes email drafts |

### Google Sheets setup (only for `sheet` mode)

1. Create a Google Cloud project (or use an existing one).
2. Enable the **Google Sheets API** and **Google Drive API**.
3. Create a **service account** and download its JSON key.
4. Save the JSON as `service-account.json` in the project root.
5. Create a Google Sheet with these columns in row 1 (at minimum):
   `person_name, person_email, company, property_address, city, state, country`
6. Share the Sheet with the service account's email (`xxx@yyy.iam.gserviceaccount.com`), with **Editor** access.
7. Copy the sheet ID from its URL into `.env` as `LEADS_SHEET_ID`.

The tool automatically extends your header row with the enriched output columns on first run.

## Scoring rubric

| Category | Weight | Sub-signals (data source) |
|---|---|---|
| **Fit** | 30% | Company Type (Wikipedia) • Role Seniority (email heuristic) • Market Tier (static mapping) • Company Scale (Wikipedia) |
| **Value** | 25% | Rent Level (Census) • Lead Volume (Census) • Location Premium (WalkScore) • Upsell Potential (Wikipedia) |
| **Timing** | 25% | Trigger Event (NewsAPI) • News Velocity (NewsAPI) • Seasonality (calendar) |
| **Intent** | 20% | Email Quality (heuristic) • Digital Activity (NewsAPI + Wikipedia) |

**Tiers:** Hot ≥ 80 · Warm 60–79 · Cool 40–59 · Cold < 40.

Final formula:
```
score = 10 × (0.30 × Fit + 0.25 × Value + 0.25 × Timing + 0.20 × Intent)
```
Each category score is the simple average of its sub-signals on a 0–10 scale.

### Experimenting with weights

You can try alternative weight schemes without touching code or re-running enrichment:

```bash
# First, enrich and save to JSON
python -m src.main demo --json-out enriched.json

# Then compare your current weights against other schemes
python -m src.sensitivity compare enriched.json

# Or rescore with a specific custom weighting
python -m src.sensitivity rescore enriched.json \
    --weights fit=0.40 value=0.25 timing=0.20 intent=0.15
```

When you're happy with a weight set, update `CATEGORY_WEIGHTS` in `src/config.py`.

## Automation

### Scheduled runs

`.github/workflows/enrich-leads.yml` runs daily at **13:00 UTC (≈ 9am ET)**. To enable:

1. Push this repo to GitHub.
2. In **Settings → Secrets and variables → Actions**, add the secrets:
   - `NEWSAPI_KEY` · `WALKSCORE_KEY` · `CENSUS_KEY` (optional) · `ANTHROPIC_API_KEY` (optional)
   - `GOOGLE_SA_JSON` — full contents of your service-account JSON
   - `LEADS_SHEET_ID` · `LEADS_WORKSHEET_NAME` (optional, defaults to "Leads")
3. The workflow will run automatically.

### Manual trigger

Actions tab → **Enrich Leads** → **Run workflow**.

### Re-processing errored rows

If some rows errored (e.g., a transient NewsAPI hiccup), reset them and re-run:

```bash
python -m src.main reset-sheet --only error
python -m src.main sheet
```

Use `--only all` to reset every row.

## Reliability features

| Concern | How it's handled |
|---|---|
| Transient API failures | Centralized HTTP client with exponential backoff on 408/429/5xx (3 attempts with jitter) |
| Rate limits | Honors `Retry-After` header on 429; aggressive per-API caching (1–365 day TTLs) |
| Hard failures | Non-retryable 4xx errors fail fast; per-lead errors are captured and the batch continues |
| Missing data | Sub-signals with no data receive a neutral 5/10, not zero |
| Duplicate runs | Rows in `done` or `error` status are skipped unless explicitly reset |
| Lost caches | SQLite cache is restored between GitHub Actions runs |
| Observability | Every run produces a summary report with tier counts, API error buckets, and top leads |

## Architecture

```
src/
├── main.py              # CLI entrypoint (demo / csv / json / sheet / report / reset-sheet)
├── pipeline.py          # Per-lead orchestrator
├── config.py            # Weights, thresholds, API endpoints
├── models.py            # Dataclasses for Lead, enrichments, scoring
├── cache.py             # SQLite cache with per-API TTLs
├── http_client.py       # HTTP client with exponential-backoff retries
├── report.py            # Run-summary report (plain text + markdown)
├── sensitivity.py       # Alternative weight-scheme analyzer
├── csv_io.py            # CSV reader/writer
├── json_io.py           # JSON reader/writer
├── sheets.py            # Google Sheets reader/writer
├── insights.py          # Sales insights block generator
├── enrich/              # One module per external API
├── scoring/             # One module per scoring category
├── heuristics/          # Local heuristics (no network)
└── outreach/            # Email template selection + LLM polish

tests/
├── run_all.py             # Unified unit-test runner
├── test_scoring.py        # Heuristics + end-to-end scoring (16 tests)
├── test_http_and_report.py# Retry logic + report aggregation (9 tests)
├── test_integration.py    # Real-API tests (opt-in via RUN_INTEGRATION=1)
└── offline_demo.py        # Visual demo with realistic synthetic enrichment
```

## Running the tests

```bash
# Unit tests (no network — 25 tests)
python tests/run_all.py

# Integration tests (hits real Wikipedia + Census; no keys needed)
RUN_INTEGRATION=1 python tests/test_integration.py

# Visual demo with realistic synthetic enrichment data
python tests/offline_demo.py
```

## Limitations and v2 roadmap

Three Intent sub-signals were deliberately deferred from v1 because they would require APIs outside the free suggested list:

- **Hiring signals** (leasing/ops job postings) — needs LinkedIn Jobs or Indeed
- **Tech stack detection** (chatbot present, contact-form modernity) — needs BuiltWith or reliable scraping
- **Operational pain from reviews** (slow-response complaints) — needs Google Places or Yelp

Adding any of these is straightforward: create `src/enrich/<api>.py`, add a sub-signal to `src/scoring/intent.py`, and the rest of the pipeline picks it up automatically.

## License

Internal tool. Not for external distribution.
