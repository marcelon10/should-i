.PHONY: help setup hooks fixture ingest ingest-offline build check morning \
        lint fmt typecheck sql test ci demo docker clean

help:  ## show this help
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# --- setup ---------------------------------------------------------------
setup:          ## install the project plus dev tooling
	pip install -e ".[dev]"

hooks:          ## install git pre-commit and pre-push hooks
	pre-commit install --install-hooks
	pre-commit install --hook-type pre-push

# --- pipeline ------------------------------------------------------------
fixture:        ## regenerate the offline weather fixture
	python scripts/make_fixture.py

ingest:         ## pull live data from the API
	python -m ingestion.run weather

ingest-offline: ## replay the fixture (no network needed)
	python -m ingestion.run weather --offline

build:          ## build staging + mart models
	python -m transform.build_local

check:          ## run data quality gates
	python -m quality.checks

morning:        ## render the morning page
	python -m serving.morning

demo: fixture ingest-offline build morning  ## full offline run from scratch

# --- quality -------------------------------------------------------------
lint:           ## ruff check + format check
	ruff check .
	ruff format --check .

fmt:            ## autofix and format
	ruff check --fix .
	ruff format .
	sqlfluff fix transform/models

typecheck:      ## mypy
	mypy .

sql:            ## lint the dbt models
	sqlfluff lint transform/models

test:           ## pytest with the coverage gate
	python -m pytest

ci: lint typecheck sql test  ## everything CI runs, locally
	@echo "CI checks passed locally."

# --- container -----------------------------------------------------------
docker:         ## build the runtime image
	docker build -t should-i:local .

clean:          ## delete the warehouse, raw archive, and caches
	rm -rf data/warehouse data/raw coverage.xml .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache
