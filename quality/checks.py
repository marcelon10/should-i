"""
Data quality gates.

These run *between* transform and serving. The contract is simple: if a
blocking check fails, the morning page refuses to render a verdict rather
than confidently telling you to bike into a storm. A silently-stale
dashboard is worse than an obviously-broken one.

    python -m quality.checks
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import timedelta

from config.clock import local_today
from storage import warehouse as wh

FRESHNESS_LIMIT_HOURS = 24
MIN_HOURS_PER_DAY = 20  # a day with fewer hours than this is incomplete


@dataclass
class CheckResult:
    name: str
    passed: bool
    blocking: bool
    detail: str

    @property
    def icon(self) -> str:
        if self.passed:
            return "PASS"
        return "FAIL" if self.blocking else "WARN"


def run_checks() -> list[CheckResult]:
    results: list[CheckResult] = []

    with wh.warehouse() as con:
        # 1. Freshness — is the newest ingest recent enough to trust?
        row = con.execute("SELECT max(ingested_at) FROM raw_weather_hourly").fetchone()
        latest = row[0] if row else None
        if latest is None:
            results.append(CheckResult("freshness", False, True, "no data at all"))
        else:
            age = wh.utcnow() - latest
            ok = age < timedelta(hours=FRESHNESS_LIMIT_HOURS)
            results.append(
                CheckResult(
                    "freshness",
                    ok,
                    True,
                    f"last ingest {age.total_seconds() / 3600:.1f}h ago "
                    f"(limit {FRESHNESS_LIMIT_HOURS}h)",
                )
            )

        # 2. Coverage — do we actually have today in the forecast?
        today = local_today()
        n = wh.scalar(
            con,
            "SELECT count(*) FROM daily_conditions WHERE valid_date = ?",
            [today],
        )
        results.append(
            CheckResult("today_present", n > 0, True, f"{n} row(s) for {today}")
        )

        # 3. Completeness — partial days produce misleading aggregates
        incomplete = con.execute(
            "SELECT valid_date, hours_observed FROM daily_conditions "
            "WHERE hours_observed < ? ORDER BY valid_date",
            [MIN_HOURS_PER_DAY],
        ).fetchall()
        results.append(
            CheckResult(
                "day_completeness",
                not incomplete,
                False,
                "all days complete"
                if not incomplete
                else f"{len(incomplete)} partial day(s): {incomplete[:3]}",
            )
        )

        # 4. Range sanity — catches unit swaps and upstream schema changes
        bad = wh.scalar(
            con,
            "SELECT count(*) FROM raw_weather_hourly WHERE "
            "temperature_c IS NULL OR temperature_c NOT BETWEEN -60 AND 60 "
            "OR precipitation_prob NOT BETWEEN 0 AND 100 "
            "OR wind_speed_kmh < 0",
        )
        results.append(
            CheckResult("value_ranges", bad == 0, True, f"{bad} out-of-range row(s)")
        )

        # 5. Uniqueness — the grain must hold or every aggregate is wrong
        dupes = wh.scalar(
            con,
            "SELECT count(*) FROM ("
            "  SELECT location_name, valid_at FROM raw_weather_hourly"
            "  GROUP BY 1, 2 HAVING count(*) > 1)",
        )
        results.append(
            CheckResult("grain_unique", dupes == 0, True, f"{dupes} duplicate key(s)")
        )

    return results


def gate() -> bool:
    """True if it is safe to serve. Prints a report either way."""
    results = run_checks()
    for r in results:
        print(f"  [{r.icon}] {r.name:18} {r.detail}")
    return all(r.passed for r in results if r.blocking)


if __name__ == "__main__":
    print("data quality:")
    sys.exit(0 if gate() else 1)
