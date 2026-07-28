"""
End-to-end: ingest -> transform -> quality -> serve, entirely offline.

This is the test that would actually have caught every outage I can imagine
in a pipeline this size. Unit tests prove each part works; this proves the
seams between them line up, which is where pipelines really break.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.clock import local_today
from config.settings import LOCATION
from ingestion import run as ingest
from quality import checks
from serving import morning
from storage import warehouse as wh
from transform import build_local


def _write_fixture(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "weather.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture
def pipeline_run(isolated_env, fixture_payload, monkeypatch):
    """Run the whole pipeline once against a temporary warehouse."""
    path = _write_fixture(isolated_env, fixture_payload)
    monkeypatch.setattr(
        "ingestion.sources.weather.load_fixture",
        lambda p=None: json.loads(path.read_text(encoding="utf-8")),
    )
    written = ingest.run_weather(offline=True)
    build_local.main()
    return written


def test_pipeline_loads_and_builds(pipeline_run):
    assert pipeline_run == 48  # 2 forecast days x 24 hours

    with wh.warehouse() as con:
        staged = wh.scalar(con, "SELECT count(*) FROM stg_weather_hourly")
        marts = wh.scalar(con, "SELECT count(*) FROM daily_conditions")
    assert staged == 48
    assert marts == 2


def test_pipeline_is_idempotent_end_to_end(pipeline_run, isolated_env, monkeypatch):
    """Running the entire pipeline twice must not double any row."""
    ingest.run_weather(offline=True)
    build_local.main()

    with wh.warehouse() as con:
        raw = wh.scalar(con, "SELECT count(*) FROM raw_weather_hourly")
        marts = wh.scalar(con, "SELECT count(*) FROM daily_conditions")
        runs = wh.scalar(con, "SELECT count(*) FROM ingestion_runs")
    assert raw == 48
    assert marts == 2
    assert runs == 2  # two runs recorded, zero duplicated data


def test_run_bookkeeping_records_success(pipeline_run):
    with wh.warehouse() as con:
        row = con.execute(
            "SELECT status, rows_written FROM ingestion_runs "
            "ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    assert row is not None
    status, rows = row
    assert status == "success"
    assert rows == 48


def test_raw_payload_is_archived(pipeline_run, isolated_env):
    """The immutable archive is the whole replay story — assert it exists."""
    archived = list((isolated_env / "raw" / "weather").rglob("*.json"))
    assert len(archived) == 1
    assert json.loads(archived[0].read_text())["hourly"]["time"]


def test_quality_gate_passes_on_good_data(pipeline_run, capsys):
    assert checks.gate() is True


def test_quality_gate_blocks_on_corrupt_data(pipeline_run, capsys):
    """Poison the warehouse; the gate must refuse to let it through."""
    with wh.warehouse() as con:
        con.execute("UPDATE raw_weather_hourly SET temperature_c = 999")
    assert checks.gate() is False
    assert "value_ranges" in capsys.readouterr().out


def test_quality_gate_detects_missing_today(isolated_env, capsys):
    """Empty warehouse: freshness and coverage must both fail, not crash."""
    with wh.warehouse() as con:
        con.execute(
            "CREATE OR REPLACE TABLE daily_conditions "
            "(location_name VARCHAR, valid_date DATE, hours_observed INT)"
        )
    assert checks.gate() is False


def test_morning_page_renders(pipeline_run, capsys):
    exit_code = morning.render()
    out = capsys.readouterr().out
    assert exit_code == 0
    assert LOCATION.name in out
    assert "bike to work?" in out
    assert "run outside?" in out


def test_morning_page_refuses_bad_data(pipeline_run, capsys):
    with wh.warehouse() as con:
        con.execute("UPDATE raw_weather_hourly SET temperature_c = 999")
    exit_code = morning.render()
    assert exit_code == 1
    assert "Refusing" in capsys.readouterr().out


def test_morning_page_handles_missing_day(pipeline_run, capsys):
    """A date with no forecast should say so, not raise."""
    from datetime import timedelta

    exit_code = morning.render(local_today() + timedelta(days=90))
    assert exit_code == 1


def test_fetch_day_returns_none_for_unknown_date(pipeline_run):
    from datetime import date

    assert morning.fetch_day(date(1999, 1, 1)) is None
