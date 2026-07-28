"""
Tests that run with no network and no shared state.

The three things worth testing in a pipeline this size:
  1. the pure transform (normalize) handles ragged real-world payloads
  2. loading is genuinely idempotent
  3. the business rules fire on the right side of each threshold
"""

from __future__ import annotations

from datetime import datetime

import pytest

from config.settings import THRESHOLDS
from ingestion.sources import weather
from serving.morning import bike_verdict, run_verdict
from storage import warehouse as wh


# --- normalize ----------------------------------------------------------
def test_normalize_flattens_columnar_payload():
    payload = {
        "hourly": {
            "time": ["2026-07-27T00:00", "2026-07-27T01:00"],
            "temperature_2m": [15.0, 14.2],
            "precipitation_probability": [10, 20],
            "wind_speed_10m": [8.0, 9.5],
        }
    }
    rows = weather.normalize(payload, "Testville")
    assert len(rows) == 2
    assert rows[0]["valid_at"] == datetime(2026, 7, 27, 0, 0)
    assert rows[1]["temperature_c"] == 14.2
    assert rows[0]["location_name"] == "Testville"


def test_normalize_tolerates_short_arrays():
    """Upstream sometimes returns fewer values than timestamps."""
    payload = {
        "hourly": {
            "time": ["2026-07-27T00:00", "2026-07-27T01:00"],
            "temperature_2m": [15.0],
            "precipitation_probability": [],
            "wind_speed_10m": [8.0],
        }
    }
    rows = weather.normalize(payload, "Testville")
    assert rows[1]["temperature_c"] is None
    assert rows[1]["precipitation_prob"] is None


def test_normalize_empty_payload_returns_no_rows():
    assert weather.normalize({}, "Testville") == []


# --- idempotency --------------------------------------------------------
@pytest.fixture
def con(tmp_path):
    connection = wh.connect(tmp_path / "test.duckdb")
    yield connection
    connection.close()


def _rows(temp: float = 20.0):
    return [
        {
            "location_name": "Testville",
            "valid_at": datetime(2026, 7, 27, h),
            "temperature_c": temp,
            "precipitation_prob": 10,
            "wind_speed_kmh": 5.0,
        }
        for h in range(24)
    ]


def test_merge_is_idempotent(con):
    wh.merge_weather_hourly(con, _rows(), "run-1")
    wh.merge_weather_hourly(con, _rows(), "run-2")
    total = con.execute("SELECT count(*) FROM raw_weather_hourly").fetchone()[0]
    assert total == 24


def test_merge_restates_on_conflict(con):
    """A newer forecast for the same hour must win, not coexist."""
    wh.merge_weather_hourly(con, _rows(temp=20.0), "run-1")
    wh.merge_weather_hourly(con, _rows(temp=31.5), "run-2")
    temps = con.execute(
        "SELECT DISTINCT temperature_c FROM raw_weather_hourly"
    ).fetchall()
    assert temps == [(31.5,)]


def test_merge_empty_is_a_noop(con):
    assert wh.merge_weather_hourly(con, [], "run-1") == 0


# --- business rules -----------------------------------------------------
def _day(**overrides):
    base = {
        "temp_min_c": 12.0,
        "temp_max_c": 22.0,
        "daylight_temp_avg_c": 18.0,
        "daylight_precip_prob_max": 20,
        "commute_precip_prob_max": 10,
        "commute_wind_max_kmh": 12.0,
        "wind_max_kmh": 18.0,
        "hours_observed": 24,
    }
    base.update(overrides)
    return base


def test_bike_yes_in_good_conditions():
    assert bike_verdict(_day()).answer is True


def test_bike_no_when_rain_exceeds_threshold():
    rainy = _day(commute_precip_prob_max=THRESHOLDS.max_bike_precip_prob + 1)
    verdict = bike_verdict(rainy)
    assert verdict.answer is False
    assert "rain" in verdict.reasons[0]


def test_bike_no_when_windy():
    gusty = _day(commute_wind_max_kmh=THRESHOLDS.max_bike_wind_kmh + 5)
    assert bike_verdict(gusty).answer is False


def test_bike_boundary_is_inclusive():
    """At exactly the threshold you still ride — off-by-one bugs live here."""
    edge = _day(commute_precip_prob_max=THRESHOLDS.max_bike_precip_prob)
    assert bike_verdict(edge).answer is True


def test_run_no_when_too_cold():
    cold = _day(daylight_temp_avg_c=THRESHOLDS.min_run_temp_c - 1)
    assert run_verdict(cold).answer is False


def test_run_no_when_too_hot():
    hot = _day(daylight_temp_avg_c=THRESHOLDS.max_run_temp_c + 1)
    assert run_verdict(hot).answer is False
