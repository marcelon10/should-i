# should-i

A personal decision engine. It ingests public signals about where you live and answers the questions you actually ask each morning: *bike or drive? good day for a run? run the dishwasher now or at 1pm?*

It exists as a way to build and operate a full data platform — ingestion, storage, transformation, quality gates, orchestration, serving — on something small enough to finish and useful enough to keep running.

```bash
make setup && make hooks && make demo
```

That runs the whole thing offline from a fresh clone, no API keys.

```
  Lisbon — Monday 27 July 2026

  data quality:
  [PASS] freshness          last ingest 0.0h ago (limit 24h)
  [PASS] today_present      1 row(s) for 2026-07-27
  [PASS] day_completeness   all days complete
  [PASS] value_ranges       0 out-of-range row(s)
  [PASS] grain_unique       0 duplicate key(s)

  8.4–23.4°C, peak rain chance 51%, max wind 23.8 km/h

  YES  bike to work?          39% rain, wind 20.6 km/h
  YES  run outside?           19.4°C, 51% rain
```

## Architecture

```
  SOURCES              INGEST            STORE                TRANSFORM           SERVE
 ┌──────────┐        ┌─────────┐      ┌────────────┐        ┌───────────┐      ┌──────────┐
 │ weather  │ batch  │ fetch   │      │ raw/*.json │        │ staging   │      │ morning  │
 │ air qual │ ─────► │ archive │ ───► │ (immutable)│  ───►  │   ↓       │ ───► │  page    │
 │ elec $$  │ incr.  │ normalize│     │            │        │ marts     │      │          │
 │ calendar │ ref.   │ merge   │      │  DuckDB    │        │ (dbt)     │      │ verdicts │
 └──────────┘        └─────────┘      └────────────┘        └───────────┘      └──────────┘
                          │                                       │                  ▲
                          │            ┌──────────────────┐       │                  │
                          └───────────►│ ingestion_runs   │       └──────────────────┘
                                       │ (run bookkeeping)│          quality gates
                                       └──────────────────┘          block on failure

                  ── orchestrated by Dagster: schedule, retry, backfill ──
```

Three ideas hold the whole design together:

**Raw is immutable.** Every API payload is archived to disk untouched before anything parses it. When you find a bug in `normalize()` six weeks from now, you replay the archive instead of losing the history.

**Loads are idempotent.** Forecasts are restatements — today's prediction for tomorrow gets superseded tomorrow morning. `merge_weather_hourly` upserts on `(location_name, valid_at)`, so re-running any pipeline any number of times converges to the same state. This is enforced in the storage layer, not left to each source to remember.

**Facts and preferences are separated.** The mart contains only measurements. Your thresholds (`max_bike_aqi`, `max_run_temp_c`) live in `config/settings.py` and are applied at serving time. Change your mind about what counts as too windy and you edit one line — no backfill.

## Layout

```
config/settings.py         location, thresholds, source registry
ingestion/
  sources/weather.py       fetch() · archive() · normalize()  ← normalize is pure
  run.py                   CLI entrypoint, run bookkeeping
storage/warehouse.py       DuckDB connection, DDL, idempotent merge
transform/
  models/staging/          rename, cast, clean — no business logic
  models/marts/            daily_conditions, one row per location-day
  models/schema.yml        dbt tests: not_null, ranges, grain uniqueness
  build_local.py           runs the models without dbt installed
quality/checks.py          freshness · coverage · completeness · ranges · grain
serving/morning.py         applies thresholds, renders verdicts
orchestration/definitions.py   Dagster assets, schedule, blocking asset check
tests/test_pipeline.py     12 tests, no network, no shared state
```

## Engineering practice

The pipeline is small on purpose; the discipline around it is not. Everything
below runs locally in about twenty seconds via `make ci`, and again in GitHub
Actions on every push.

| Concern | Tool | Where it runs |
|---|---|---|
| Lint, imports, security lint | ruff | pre-commit + CI |
| Formatting | ruff format | pre-commit + CI |
| Types | mypy | pre-commit + CI |
| SQL style | sqlfluff | pre-commit + CI |
| Tests, coverage ≥ 90% | pytest, pytest-cov | pre-push + CI |
| Full offline pipeline run | make | CI |
| Idempotency after a double run | assert_idempotent.py | CI |
| Leaked secrets | gitleaks | pre-commit + CI |
| Dependency CVEs | pip-audit, Dependabot | CI + weekly |
| Container publish | Docker → GHCR, signed | on tag |

Three choices worth explaining:

**A single `CI passed` aggregator job.** Branch protection requires only that
one check. It depends on all the others, so adding a job makes it blocking
automatically — you can't forget to update a settings page.

**The linter found a real bug.** ruff's `DTZ011` flagged `date.today()`, which
returns the *server's* today. Running in a UTC runner at 23:30 Lisbon time, the
pipeline would have asked for tomorrow's date and reported no data — a failure
appearing only at night, only in CI, only sometimes. `config/clock.py` exists
because of that catch.

**CD for a data project means the pipeline actually runs.** `scheduled-run.yml`
executes it daily against the live API, publishes the brief to the run summary,
persists the warehouse between runs, and opens a GitHub issue when anything
fails. A pipeline nobody notices breaking is not deployed.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the branch protection settings and
the checklist for adding a new source.

## Commands

| | |
|---|---|
| `make demo` | full offline run from scratch |
| `make ingest` | pull live data from the API |
| `make ingest-offline` | replay the local fixture |
| `make build` | build staging + marts |
| `make check` | run data quality gates |
| `make morning` | render the morning page |
| `make test` | tests with the coverage gate |
| `make ci` | lint + types + SQL + tests, everything CI runs |
| `make fmt` | autofix Python and SQL |
| `make hooks` | install git pre-commit and pre-push hooks |
| `make docker` | build the runtime image |

## Roadmap

Each phase is a working milestone, not a refactor.

**Phase 1 — one source, done properly** ✅
Batch weather ingestion, immutable raw archive, idempotent merge, run bookkeeping, tests.
*Learn: idempotency, raw/clean separation, replayability.*

**Phase 1.5 — CI/CD before the codebase grows** ✅
Lint, types, SQL style, 90% coverage gate, matrix testing, secret and CVE
scanning, scheduled production runs with failure alerting, signed containers.
*Learn: making correctness automatic instead of remembered.*

**Phase 2 — dbt and a second source**
Install `dbt-duckdb`, delete `build_local.py`, run `dbt build`. Add OpenAQ air quality — different latency, different grain, late-arriving rows. Join into `daily_conditions`.
*Learn: dimensional modeling, incremental models, source freshness, schema tests.*

**Phase 3 — orchestration**
`orchestration/definitions.py` is already written. Install Dagster, run `dagster dev`, get a DAG with schedules, retries, backfills, and a blocking quality check.
*Learn: dependency graphs, failure handling, backfills.*

**Phase 4 — observability**
Alert when a source goes stale. Track run duration over time. Add freshness SLAs per source and a `pipeline_health` mart built from `ingestion_runs`.
*Learn: monitoring your own pipelines instead of finding out from the dashboard.*

**Phase 5 — more decisions**
Day-ahead electricity prices → "cheapest 2-hour window to run the dishwasher." Calendar export → "you have a 9am, leave by 8:20."
*Learn: joining sources with genuinely different shapes and update cadences.*

**Phase 6 — streaming, or ML**
GTFS-realtime transit into Kafka for a real streaming path. Or log whether you *actually* biked, and train a model on regret.
*Learn: streaming semantics, or the feature-store problem.*

## Setup

Change `LOCATION` in `config/settings.py` to your coordinates, and `THRESHOLDS` to your tolerances. Then `make demo`.

Open-Meteo requires no API key and is free for non-commercial use.
