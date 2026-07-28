# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [SemVer](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- CI/CD: ruff, mypy, sqlfluff, pre-commit hooks, coverage gate at 90%
- CI matrix across Python 3.11 / 3.12 / 3.13, with an aggregator `CI passed` job
- Scheduled daily pipeline workflow that opens an issue on failure
- Multi-stage Dockerfile, non-root runtime, GHCR publishing with provenance
- gitleaks secret scanning and pip-audit dependency auditing
- `config/clock.py` — timezone-correct `local_today()`
- `storage.scalar()` — typed single-value query helper
- End-to-end test suite covering quality-gate blocking and idempotency

### Fixed
- `date.today()` used the server timezone, which would report the wrong day
  when the pipeline ran late-evening local time in a UTC CI runner

## [0.1.0] - 2026-07-27

### Added
- Phase 1: idempotent weather ingestion, immutable raw archive, run
  bookkeeping, staging + mart models, five quality gates, morning page
