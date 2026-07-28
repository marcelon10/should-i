# should-i — working context for Claude Code

A personal decision engine built as a full data-engineering platform. The
pipeline is small on purpose; the discipline around it is the point. This file
records *why* things are the way they are — the rationale and the pitfalls, not
the layout (read the tree yourself) or the dependency list (read pyproject.toml).

The maintainer is learning data engineering and CI/CD. Explain reasoning, not
just commands. Prefer teaching the "why" over hand-waving.

## Commands

- `make ci` runs everything CI runs: ruff, mypy, sqlfluff, pytest. Run it before pushing.
- `make demo` runs the whole pipeline offline from scratch (no network, no keys).
- `make fmt` autofixes Python and SQL formatting.
- Individual stages: `make ingest-offline`, `make build`, `make check`, `make morning`.

## Load-bearing design decisions — do not silently undo these

1. **Facts and preferences are separated.** Marts contain only measurements.
   Personal thresholds (bike/run cutoffs) live in `config/settings.py` and are
   applied at *serving* time, never baked into the warehouse. Reason: preferences
   change often; baking them in would force a backfill every time. If asked to
   add a threshold to a mart, push back and keep it in config.

2. **Idempotency lives in the storage layer**, not in each source. Every load is
   an upsert on the natural key, so re-running any pipeline any number of times
   converges to the same state. New sources MUST merge on their natural key, not
   append. Forecasts are restatements — last write wins.

3. **Raw is immutable.** Every API payload is archived untouched to disk before
   anything parses it, so history can be replayed if `normalize()` has a bug.

4. **`normalize()` functions must stay pure** (payload in, rows out, no I/O).
   That is what makes them testable without a network call. Keep `fetch()` and
   `normalize()` separate in every source.

5. **Quality gates block, they don't warn.** If a blocking check fails, the
   morning page refuses to render a verdict rather than showing stale/bad data.

## Pitfalls already hit (don't repeat them)

- **Timezones:** never use `date.today()` or naive `datetime.now()`. Use the
  helpers in `config/clock.py` (`local_today`, `local_now`, `utcnow`). A
  server-timezone `date.today()` caused a real "wrong day" bug in UTC CI runners.
  Storage timestamps are UTC; anything human-facing or day-keyed is local tz.
- **`duckdb` fetchone() returns Optional** — use `storage.warehouse.scalar()`
  for single-value queries instead of indexing `.fetchone()[0]`, which mypy
  (correctly) rejects and which crashes on an empty table.
- **gitleaks pre-commit hook crashes locally** (wasm error on this Linux box).
  It was removed from `.pre-commit-config.yaml`; secret scanning still runs in
  CI where it works. Don't re-add the local hook.
- **pip-audit / setuptools:** CI upgrades setuptools before auditing to clear
  an sdist CVE that doesn't actually apply to us (we don't publish sdists).

## Conventions

- Conventional Commits (`feat:`, `fix:`, `ci:`, `docs:`, scopes match packages).
- Never commit to `main` directly; branch + PR. `main` is protected, requires
  the `CI passed` aggregator check.
- Requires Python 3.11+ (`datetime.UTC`, `zip(strict=)`). CI matrix: 3.11–3.13.
- When adding a data source, follow the checklist in CONTRIBUTING.md.

## Roadmap

Phase 1 (weather ingestion) and 1.5 (CI/CD) are done. Next is phase 2: install
`dbt-duckdb`, retire `transform/build_local.py` in favour of real `dbt build`,
and add OpenAQ air quality as a second source with a different latency and grain.
See README.md for the full phase breakdown.

## Fuller narrative

The design history and the reasoning behind the CI/CD setup are in
`docs/design-history.md` — read it if you need background on a decision that
isn't explained here, but it is not auto-loaded.
