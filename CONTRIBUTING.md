# Contributing

Written for future-me, six months from now, who has forgotten all of this.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
make setup     # installs the project plus dev tooling
make hooks     # installs pre-commit and pre-push git hooks
make ci        # everything CI runs, locally, in ~20 seconds
```

## The loop

```
edit → pre-commit blocks the obvious stuff at `git commit`
     → pytest blocks the rest at `git push`
     → CI runs the same checks plus the matrix and security scans
```

The rule is that **CI must never be the first place a failure appears.** If
CI catches something pre-commit could have, add it to `.pre-commit-config.yaml`.
The point of the local hooks is that a red CI badge means something real
happened, not that someone forgot a trailing newline.

## Branch protection

The repo settings that make the above enforceable, rather than aspirational:

Settings → Branches → add a rule for `main`:

- Require a pull request before merging
- Require status checks to pass → select **`CI passed`** only
- Require branches to be up to date before merging
- Require conversation resolution before merging
- Do not allow bypassing the above (yes, including yourself)
- Restrict force pushes and deletions

Select only `CI passed`. It is an aggregator job that depends on every other
job, so adding a new job to `ci.yml` makes it blocking automatically. Listing
each job individually means the day you add a job, it silently is not required.

## Commits

Conventional Commits, because `release.yml` generates release notes from them:

```
feat(ingestion): add OpenAQ air quality source
fix(quality): freshness check used server time, not local
chore(deps): bump duckdb to 1.5
docs(readme): document the phase 3 rollout
refactor(storage): extract scalar() helper
test(e2e): cover the corrupt-data path
```

Scopes match the top-level packages: `ingestion`, `storage`, `transform`,
`quality`, `serving`, `orchestration`.

## What CI enforces

| Check | Tool | Blocking |
|---|---|---|
| Lint + import order + security lint | ruff | yes |
| Formatting | ruff format | yes |
| Types | mypy | yes |
| SQL style | sqlfluff | yes |
| Tests on 3.11 / 3.12 / 3.13 | pytest | yes |
| Coverage ≥ 90% | pytest-cov | yes |
| Full offline pipeline run | make | yes |
| Idempotency after a double run | assert_idempotent.py | yes |
| Leaked secrets in history | gitleaks | yes |
| Known CVEs in dependencies | pip-audit | yes |
| dbt build | dbt | not yet (phase 2) |

## Adding a data source

The checklist that keeps the pipeline trustworthy as it grows:

1. `ingestion/sources/<name>.py` with `fetch()`, `archive()`, and a **pure**
   `normalize()`. Purity is what makes it testable without a network call.
2. A merge function in `storage/warehouse.py` keyed on the natural key.
   Idempotency is the storage layer's job, not the source's.
3. Register it in `SOURCES` in `config/settings.py`.
4. A staging model, then join it into a mart. Facts only — no thresholds.
5. Quality checks: freshness SLA, range sanity, grain uniqueness.
6. A fixture in `tests/fixtures/` so CI stays offline, plus tests for the
   ragged-payload case. Upstream *will* return short arrays eventually.
7. An entry in the README roadmap.

## Releasing

```bash
git tag -a v0.2.0 -m "phase 2: dbt + air quality"
git push --tags
```

That triggers `release.yml`, which reruns the full CI suite, builds and scans
the container, pushes it to GHCR with provenance attestation, and drafts a
GitHub release. Nothing gets published from a commit that has not passed CI.
