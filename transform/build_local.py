"""
Run the dbt models against DuckDB *without* dbt installed.

The point is not to reimplement dbt — it's so the repo is runnable end to end
from a fresh clone (and in CI) while phase 2 is still in progress. The .sql
files stay the single source of truth: this resolves {{ ref() }} and
{{ source() }} to table names and executes them in dependency order. When you
install dbt for real, delete this file and nothing else changes.

    python -m transform.build_local
"""

from __future__ import annotations

import re
from pathlib import Path

from storage import warehouse as wh

MODELS_DIR = Path(__file__).resolve().parent / "models"

REF = re.compile(r"\{\{\s*ref\(\s*['\"](\w+)['\"]\s*\)\s*\}\}")
SOURCE = re.compile(
    r"\{\{\s*source\(\s*['\"](\w+)['\"]\s*,\s*['\"](\w+)['\"]\s*\)\s*\}\}"
)

# staging first, then marts — a real DAG parse is overkill for two layers
BUILD_ORDER = [
    ("staging/stg_weather_hourly.sql", "view"),
    ("marts/daily_conditions.sql", "table"),
]


def compile_sql(raw: str) -> str:
    sql = SOURCE.sub(lambda m: m.group(2), raw)  # source('raw','x') -> x
    sql = REF.sub(lambda m: m.group(1), sql)  # ref('x')          -> x
    return sql


def main() -> None:
    with wh.warehouse() as con:
        for rel_path, materialization in BUILD_ORDER:
            path = MODELS_DIR / rel_path
            name = path.stem
            sql = compile_sql(path.read_text(encoding="utf-8"))
            keyword = "VIEW" if materialization == "view" else "TABLE"
            con.execute(f"CREATE OR REPLACE {keyword} {name} AS {sql}")
            # Safe: `name` comes from BUILD_ORDER, a hardcoded
            # constant in this file. No user input reaches this string.
            count = wh.scalar(con, f"SELECT count(*) FROM {name}")  # noqa: S608
            print(f"built {materialization:5} {name:24} {count:>6} rows")


if __name__ == "__main__":
    main()
