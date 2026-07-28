"""
Generate an offline weather fixture anchored to today's date.

Why: the repo should be runnable with zero network access (CI, planes,
rate limits) and a fixture with hard-coded 2023 timestamps goes stale.
This produces a payload shaped exactly like Open-Meteo's response.
"""

from __future__ import annotations

import json
import math
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "weather.json"


def build(days: int = 2, seed: int = 7) -> dict:
    rng = random.Random(seed)  # noqa: S311 - synthetic test data, not crypto
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    hours = days * 24

    times, temps, precip, wind = [], [], [], []
    for h in range(hours):
        ts = start + timedelta(hours=h)
        # crude diurnal curve peaking mid-afternoon
        curve = math.sin((ts.hour - 6) / 24 * 2 * math.pi)
        times.append(ts.strftime("%Y-%m-%dT%H:%M"))
        temps.append(round(16 + 7 * curve + rng.uniform(-1, 1), 1))
        precip.append(max(0, min(100, int(25 + 30 * rng.random() - 15 * curve))))
        wind.append(round(max(0.0, 12 + 10 * rng.random() + 4 * curve), 1))

    return {
        "latitude": 38.72,
        "longitude": -9.14,
        "timezone": "Europe/Lisbon",
        "hourly_units": {
            "temperature_2m": "°C",
            "precipitation_probability": "%",
            "wind_speed_10m": "km/h",
        },
        "hourly": {
            "time": times,
            "temperature_2m": temps,
            "precipitation_probability": precip,
            "wind_speed_10m": wind,
        },
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=2), encoding="utf-8")
    print(f"wrote {OUT}")
