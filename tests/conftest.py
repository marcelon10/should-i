"""
Shared fixtures.

The important one is `isolated_env`: every test gets its own warehouse and
raw archive in a tmp_path. Tests that share a database pass in isolation,
fail in CI, and pass again when you rerun them — the worst possible failure
mode. Isolation is cheap here, so it is not optional.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import ingestion.sources.weather as weather_mod
import storage.warehouse as wh_mod


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the warehouse and raw archive into a throwaway directory."""
    warehouse_path = tmp_path / "warehouse" / "test.duckdb"
    monkeypatch.setattr(wh_mod, "WAREHOUSE_PATH", warehouse_path)
    monkeypatch.setattr(weather_mod, "RAW_DIR", tmp_path / "raw")
    return tmp_path


@pytest.fixture
def fixture_payload() -> dict:
    """The offline weather payload, generated fresh so dates are current."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from make_fixture import build  # type: ignore[import-not-found]

    return build()
