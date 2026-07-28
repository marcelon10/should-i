"""
Weather source (Open-Meteo — free, no API key).

Separation of concerns on purpose:
  fetch()     -> talks to the network, returns the raw payload untouched
  normalize() -> pure function, payload -> list[dict] rows
Keeping normalize() pure is what makes the transform unit-testable without
a network call, and lets you replay an archived payload at any time.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import requests

from config.settings import LOCATION, RAW_DIR, SOURCES, Location

TIMEOUT = 20
SOURCE = SOURCES["weather"]


def fetch(location: Location = LOCATION) -> dict[str, Any]:
    """Call the forecast API and return the parsed JSON payload."""
    params = {
        "latitude": location.latitude,
        "longitude": location.longitude,
        "timezone": location.timezone,
        **SOURCE.params,
    }
    response = requests.get(SOURCE.base_url, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return cast(dict[str, Any], response.json())


def archive(payload: dict[str, Any], run_id: str) -> Path:
    """
    Write the untouched payload to the raw landing zone.

    Cheap insurance: if you later discover a bug in normalize(), you can
    rebuild history from these files instead of losing the data forever.
    """
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    out_dir = RAW_DIR / "weather" / day
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{run_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def normalize(payload: dict[str, Any], location_name: str) -> list[dict]:
    """Flatten Open-Meteo's columnar hourly block into row dicts."""
    hourly = payload.get("hourly") or {}
    times = hourly.get("time") or []

    temps = hourly.get("temperature_2m") or []
    precip = hourly.get("precipitation_probability") or []
    wind = hourly.get("wind_speed_10m") or []

    def at(seq: list, i: int):
        return seq[i] if i < len(seq) else None

    rows: list[dict] = []
    for i, ts in enumerate(times):
        rows.append(
            {
                "location_name": location_name,
                "valid_at": datetime.fromisoformat(ts),
                "temperature_c": at(temps, i),
                "precipitation_prob": at(precip, i),
                "wind_speed_kmh": at(wind, i),
            }
        )
    return rows


def load_fixture(path: Path | None = None) -> dict[str, Any]:
    """Offline payload, so the pipeline is runnable with no network."""
    fixture = path or (
        Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "weather.json"
    )
    return cast(dict[str, Any], json.loads(fixture.read_text(encoding="utf-8")))
