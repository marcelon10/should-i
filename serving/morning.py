"""
The product: a morning page that answers "should I?"

This is the only layer that knows your preferences. It reads facts from the
mart, applies THRESHOLDS, and renders verdicts with the reason attached —
a recommendation you can't interrogate is one you'll stop trusting.

    python -m serving.morning
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date

from config.clock import local_today
from config.settings import LOCATION, THRESHOLDS
from quality.checks import gate
from storage import warehouse as wh


@dataclass
class Verdict:
    question: str
    answer: bool
    reasons: list[str]

    def render(self) -> str:
        mark = "YES" if self.answer else "NO "
        why = "; ".join(self.reasons) if self.reasons else "conditions look fine"
        return f"  {mark}  {self.question:22} {why}"


def fetch_day(target: date) -> dict | None:
    with wh.warehouse() as con:
        row = con.execute(
            """
            SELECT temp_min_c, temp_max_c, daylight_temp_avg_c,
                   daylight_precip_prob_max, commute_precip_prob_max,
                   commute_wind_max_kmh, wind_max_kmh, hours_observed
            FROM daily_conditions
            WHERE location_name = ? AND valid_date = ?
            """,
            [LOCATION.name, target],
        ).fetchone()
    if not row:
        return None
    keys = [
        "temp_min_c",
        "temp_max_c",
        "daylight_temp_avg_c",
        "daylight_precip_prob_max",
        "commute_precip_prob_max",
        "commute_wind_max_kmh",
        "wind_max_kmh",
        "hours_observed",
    ]
    return dict(zip(keys, row, strict=True))


def bike_verdict(day: dict) -> Verdict:
    reasons: list[str] = []
    rain = day["commute_precip_prob_max"] or 0
    wind = day["commute_wind_max_kmh"] or 0.0

    if rain > THRESHOLDS.max_bike_precip_prob:
        reasons.append(f"{rain}% rain at commute time")
    if wind > THRESHOLDS.max_bike_wind_kmh:
        reasons.append(f"gusts to {wind} km/h")
    if not reasons:
        reasons.append(f"{rain}% rain, wind {wind} km/h")
    return Verdict(
        "bike to work?",
        not any(
            [
                rain > THRESHOLDS.max_bike_precip_prob,
                wind > THRESHOLDS.max_bike_wind_kmh,
            ]
        ),
        reasons,
    )


def run_verdict(day: dict) -> Verdict:
    reasons: list[str] = []
    temp = day["daylight_temp_avg_c"]
    rain = day["daylight_precip_prob_max"] or 0

    too_cold = temp is not None and temp < THRESHOLDS.min_run_temp_c
    too_hot = temp is not None and temp > THRESHOLDS.max_run_temp_c
    if too_cold:
        reasons.append(f"only {temp}°C")
    if too_hot:
        reasons.append(f"{temp}°C is brutal")
    if not reasons:
        reasons.append(f"{temp}°C, {rain}% rain")
    return Verdict("run outside?", not (too_cold or too_hot), reasons)


def render(target: date | None = None) -> int:
    target = target or local_today()

    print(f"\n  {LOCATION.name} — {target:%A %d %B %Y}\n")
    print("  data quality:")
    if not gate():
        print("\n  Refusing to give a verdict on data that failed its checks.\n")
        return 1

    day = fetch_day(target)
    if not day:
        print(f"\n  No mart row for {target}. Run ingestion + transform first.\n")
        return 1

    print(
        f"\n  {day['temp_min_c']}–{day['temp_max_c']}°C, "
        f"peak rain chance {day['daylight_precip_prob_max']}%, "
        f"max wind {day['wind_max_kmh']} km/h\n"
    )
    for verdict in (bike_verdict(day), run_verdict(day)):
        print(verdict.render())
    print()
    return 0


if __name__ == "__main__":
    sys.exit(render())
