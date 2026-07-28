"""
Warehouse access layer (DuckDB).

Design notes
------------
* Two logical layers live in one file-based warehouse:
    raw_*    -> append-only landing tables, source-shaped, never edited
    stg_/mart_ -> built by dbt on top of raw
* Every load is idempotent: re-running the same ingestion for the same
  (source, natural key) replaces rather than duplicates. That is the single
  most important property of a batch pipeline, so it is enforced here
  rather than left to each source.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

import duckdb

from config.clock import utcnow
from config.settings import WAREHOUSE_PATH

DDL = """
CREATE TABLE IF NOT EXISTS raw_weather_hourly (
    location_name        VARCHAR   NOT NULL,
    valid_at             TIMESTAMP NOT NULL,   -- natural key (with location)
    temperature_c        DOUBLE,
    precipitation_prob   INTEGER,
    wind_speed_kmh       DOUBLE,
    ingested_at          TIMESTAMP NOT NULL,
    source_run_id        VARCHAR   NOT NULL,
    PRIMARY KEY (location_name, valid_at)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id        VARCHAR PRIMARY KEY,
    source        VARCHAR   NOT NULL,
    started_at    TIMESTAMP NOT NULL,
    finished_at   TIMESTAMP,
    status        VARCHAR   NOT NULL,   -- running | success | failed
    rows_written  INTEGER,
    message       VARCHAR
);
"""


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open (and if needed create) the warehouse."""
    target = Path(path or WAREHOUSE_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(target))
    con.execute(DDL)
    return con


@contextlib.contextmanager
def warehouse(path: Path | None = None) -> Iterator[duckdb.DuckDBPyConnection]:
    con = connect(path)
    try:
        yield con
    finally:
        con.close()


__all__ = [
    "connect",
    "finish_run",
    "merge_weather_hourly",
    "scalar",
    "start_run",
    "utcnow",
    "warehouse",
]


def scalar(con: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> Any:
    """
    Run a query expected to return exactly one value.

    DuckDB's fetchone() is typed as Optional, and mypy is right to insist:
    a query against a dropped table really does return None. Failing loudly
    here beats an opaque `NoneType is not subscriptable` three frames away.
    """
    row = con.execute(sql, params or []).fetchone()
    if row is None:
        raise RuntimeError(f"query returned no rows: {sql.strip()[:80]}")
    return row[0]


# --- run bookkeeping ----------------------------------------------------
def start_run(con: duckdb.DuckDBPyConnection, run_id: str, source: str) -> None:
    con.execute(
        "INSERT OR REPLACE INTO ingestion_runs "
        "(run_id, source, started_at, status) VALUES (?, ?, ?, 'running')",
        [run_id, source, utcnow()],
    )


def finish_run(
    con: duckdb.DuckDBPyConnection,
    run_id: str,
    status: str,
    rows: int = 0,
    message: str | None = None,
) -> None:
    con.execute(
        "UPDATE ingestion_runs SET finished_at = ?, status = ?, "
        "rows_written = ?, message = ? WHERE run_id = ?",
        [utcnow(), status, rows, message, run_id],
    )


# --- idempotent load ----------------------------------------------------
def merge_weather_hourly(
    con: duckdb.DuckDBPyConnection,
    rows: Sequence[dict],
    run_id: str,
) -> int:
    """
    Upsert forecast rows keyed on (location_name, valid_at).

    Forecasts are *restatements*: today's 14:00 prediction for tomorrow will
    be superseded by tomorrow morning's. Last write wins, which is why this
    is a merge and not an append.
    """
    if not rows:
        return 0

    now = utcnow()
    payload = [
        (
            r["location_name"],
            r["valid_at"],
            r.get("temperature_c"),
            r.get("precipitation_prob"),
            r.get("wind_speed_kmh"),
            now,
            run_id,
        )
        for r in rows
    ]

    con.execute(
        "CREATE OR REPLACE TEMP TABLE _incoming AS "
        "SELECT * FROM raw_weather_hourly LIMIT 0"
    )
    con.executemany("INSERT INTO _incoming VALUES (?, ?, ?, ?, ?, ?, ?)", payload)

    con.execute(
        """
        DELETE FROM raw_weather_hourly t
        USING _incoming i
        WHERE t.location_name = i.location_name AND t.valid_at = i.valid_at
        """
    )
    con.execute("INSERT INTO raw_weather_hourly SELECT * FROM _incoming")
    con.execute("DROP TABLE _incoming")
    return len(payload)
