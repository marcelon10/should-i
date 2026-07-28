"""
Phase 3: orchestration.

Note how thin this is. Every asset delegates to a function that already
existed and was already tested — the orchestrator schedules and retries,
it does not own business logic. If adding Dagster had forced you to rewrite
ingestion, the seam was in the wrong place.

    pip install dagster dagster-webserver
    dagster dev -m orchestration.definitions
"""

from __future__ import annotations

from dagster import (  # type: ignore[import-not-found]
    AssetCheckResult,
    AssetExecutionContext,
    Definitions,
    RetryPolicy,
    ScheduleDefinition,
    asset,
    asset_check,
    define_asset_job,
)

from ingestion.run import run_weather
from quality.checks import run_checks
from serving.morning import render
from transform.build_local import main as build_models

RETRY = RetryPolicy(max_retries=3, delay=30)


@asset(group_name="ingestion", retry_policy=RETRY, compute_kind="python")
def raw_weather(context: AssetExecutionContext) -> None:
    """Pull the forecast and merge it into the warehouse."""
    written = run_weather()
    context.add_output_metadata({"rows_written": written})


@asset(group_name="transform", deps=[raw_weather], compute_kind="duckdb")
def marts() -> None:
    """Build staging + marts. Swap for a dbt asset once dbt is installed."""
    build_models()


@asset_check(asset=marts, blocking=True)
def quality_gate() -> AssetCheckResult:
    results = run_checks()
    blocking_failed = [r.name for r in results if r.blocking and not r.passed]
    return AssetCheckResult(
        passed=not blocking_failed,
        metadata={
            "failed": ", ".join(blocking_failed) or "none",
            "checks_run": len(results),
        },
    )


@asset(group_name="serving", deps=[marts], compute_kind="python")
def morning_page() -> None:
    render()


daily_job = define_asset_job("daily_refresh", selection="*")

defs = Definitions(
    assets=[raw_weather, marts, morning_page],
    asset_checks=[quality_gate],
    jobs=[daily_job],
    schedules=[
        ScheduleDefinition(
            job=daily_job,
            cron_schedule="0 6 * * *",
            execution_timezone="Europe/Lisbon",
        )
    ],
)
