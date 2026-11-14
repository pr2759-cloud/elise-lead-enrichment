# EliseAI Automated Inbound Lead Enrichment

Takes raw inbound leads (name, email, company, property address) and produces a **lead score**, a **decision on what to do with the lead**, an **owner**, a **personalized outreach email** where one is warranted, and a **sales insights block** — fully automated, using four free public APIs. Once sales records outcomes, it reports where pipeline comes from and **re-fits its own weights**.

## What's new in v2

v1 scored every lead and drafted an email for every lead, cold ones included. v2 adds the judgment layer:

| Gap in v1 | v2 |
|---|---|
| Every lead got an email | **Action gate**: `send` (Sniper), `review` (Scout) or `silent` (Archivist). Silent leads get no draft and no LLM call. |
| No owner | **Routing**: ordered, config-driven rules assign each lead a queue with a reason (`enterprise_ae`, `trigger_sdr`, `commercial_sdr`, `nurture`, `data_review`). |
| Missing data scored as neutral and looked like a real score | **Data confidence** per lead; below 60% resolved signals the lead is never auto-sent or silently dropped, it goes to `data_review`. |
| No Wikipedia page scored as "small company" | Treated as **unknown** scale, not small. |
| No attribution | Optional `source` / `campaign` input columns; **`pipeline-report`** shows volume, actions and conversion by source, campaign, tier, action and route. |
| Hand-set weights, never checked | `outcome` column + **`learn`**: fits weights to outcomes, validates them with 5-fold cross-validation, and only recommends them if they rank held-out leads better. |


## Excel working sheet -  

https://docs.google.com/spreadsheets/d/1MVNC1k8IdJZ1vGVEfkzat1AGg4bYe-fPpNiEwZgRT-I/edit?gid=0#gid=0

## What it does

For every inbound lead, the tool:

1. **Enriches** the lead by calling four public APIs:
   - **Wikipedia** — company notability, industry signals, portfolio-scale cues
   - **NewsAPI** — recent company news, trigger events, tech-adoption signals
   - **US Census ACS** — ZIP-level median rent, renter share, density
   - **WalkScore** — walkability, transit, and bike scores for the property
2. **Scores** the lead on a 0–100 scale using a four-category rubric (Fit / Value / Timing / Intent) with explicit sub-signals, plus a **data confidence** (share of sub-signals backed by real data).
3. **Decides** what to do: `send`, `review` or `silent` (see [Action gate](#action-gate-and-routing)).
4. **Routes** the lead to an owner, with the reason.
5. **Drafts** a personalized outreach email (send and review only) from one of five templates chosen by the dominant scoring category. With an Anthropic API key, the draft is polished by Claude Haiku. Without one, pure templates are used.
6. **Generates** a compact sales insights block organized around the four categories with concrete talking points.
7. **Writes** everything back to a Google Sheet (or CSV/JSON) and tags the row as `done`.
8. **Summarizes** every batch run with tier, action and route breakdowns, API error counts, and the top leads.

The pipeline runs automatically on a **daily schedule at 9am ET** via GitHub Actions, and can also be **manually triggered** from the Actions tab. Each run also publishes the pipeline report to the run's summary page.

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
| `python -m src.main pipeline-report enriched.csv` | Attribution + scoring check (also `.json`, or `--sheet`; `--markdown` for Slack/Notion) |
| `python -m src.main learn enriched.csv` | Fit weights to recorded outcomes and compare with current weights (`--write` to apply) |

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
   Optional (v2): `source`, `campaign` (where the lead came from) and `outcome` (filled in by sales later).
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

When you're happy with a weight set, update `CATEGORY_WEIGHTS` in `src/config.py`, or let `learn` fit one from outcomes (below).

**Missing data (v2).** A sub-signal with no data gets a neutral 5/10 so one failed API doesn't sink a lead, but it is counted as missing. `data_confidence` is the share of the 13 sub-signals backed by real data, and the action gate uses it. A company with no Wikipedia page counts as unknown scale, not small scale.

## Action gate and routing

The gate decides what happens to each lead (thresholds in `src/config.py`):

| Action | Rule | What happens |
|---|---|---|
| `review` (low data) | data confidence < 60% | Score is mostly defaults: a human looks before anything is sent or dropped |
| `silent` (Archivist) | score < 60 | Recorded in the sheet. No draft, no email, no LLM call |
| `send` (Sniper) | score ≥ 80 and a business email | Draft is ready to send |
| `review` (Scout) | everything else | Draft goes to a human first |

Routing rules are an ordered list in `ROUTING_RULES`; the first rule whose conditions all hold wins. Available conditions: `tier_in`, `action_in`, `multi_property`, `has_trigger_30d`, `free_email`, `min_confidence`, `max_confidence`. Changing who gets which leads is a config edit.

## Closing the loop: attribution and learned weights

1. Add `source` (and optionally `campaign`) to incoming leads.
2. Sales fills in `outcome` as leads resolve: `replied`, `meeting`, `demo`, `opportunity`, `won` count as positive; `no_response`, `not_interested`, `unsubscribed`, `bounced`, `lost` as negative. Blank means still open.
3. `pipeline-report` shows, by source, campaign, tier, action and route: leads, average score, what the gate did, and conversion among leads with a known outcome. Its **scoring check** says whether conversion actually falls from HOT to COLD, and flags any inversion.
4. `learn` fits a logistic regression of outcome on the four category scores, turns the coefficients into weights (each at least 5%), and scores every lead with weights fitted *without* it (5-fold cross-validation). It recommends the new weights only if they beat the current ones by at least 0.02 AUC on held-out leads, and refuses to fit below 30 labelled leads or 5 of either class.
5. `learn --write` saves `learned_weights.json`; every later run loads it and says so in the banner. Delete the file to return to the defaults. Weight changes are deliberately a manual step, not part of the scheduled job.

Outcomes for `silent` leads only exist if those leads come back on their own, so read conversion there as organic return, not as the effect of outreach.

To try it before real outcomes exist:

```bash
python tests/synthetic.py data/synthetic_outcomes.csv   # SYNTHETIC rows; timing drives conversion by construction
python -m src.main pipeline-report data/synthetic_outcomes.csv
python -m src.main learn data/synthetic_outcomes.csv
```

On the synthetic set, `learn` recovers the planted driver (Timing ≈ 0.85) and lifts held-out AUC from 0.65 to 0.86. That shows the loop works; it says nothing about what drives real conversions.

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
├── gating.py            # v2: send / review / silent decision
├── routing.py           # v2: config-driven owner assignment
├── pipeline_report.py   # v2: attribution + scoring check
├── learning.py          # v2: fit weights to outcomes, cross-validated
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
├── test_v2.py             # Gate, routing, unknown data, reports, learning (17 tests)
├── synthetic.py           # Synthetic outcome data for tests and demos
├── test_integration.py    # Real-API tests (opt-in via RUN_INTEGRATION=1)
└── offline_demo.py        # Visual demo with realistic synthetic enrichment
```

## Running the tests

```bash
# Unit tests (no network — 42 tests)
python tests/run_all.py

# Integration tests (hits real Wikipedia + Census; no keys needed)
RUN_INTEGRATION=1 python tests/test_integration.py

# Visual demo with realistic synthetic enrichment data
python tests/offline_demo.py
```

## Limitations and roadmap

Still open after v2:

- **Learned weights are linear.** `learn` re-weights the four categories; it does not learn interactions between sub-signals. With a few hundred labels, a tabular model fitted on all 13 sub-signals is the next step.
- **No reply tracking.** Outcomes are entered by sales; nothing reads replies from the mailbox yet.

Three Intent sub-signals were deliberately deferred from v1 because they would require APIs outside the free suggested list:

- **Hiring signals** (leasing/ops job postings) — needs LinkedIn Jobs or Indeed
- **Tech stack detection** (chatbot present, contact-form modernity) — needs BuiltWith or reliable scraping
- **Operational pain from reviews** (slow-response complaints) — needs Google Places or Yelp

Adding any of these is straightforward: create `src/enrich/<api>.py`, add a sub-signal to `src/scoring/intent.py`, and the rest of the pipeline picks it up automatically.

## License

Internal tool. Not for external distribution.
