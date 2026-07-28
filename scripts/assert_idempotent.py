"""
Assert that repeated pipeline runs did not duplicate data.

Called by CI after running ingest+build twice. It lives in a file rather than
a heredoc inside the workflow so that it can be run locally, linted, and type
checked like everything else. YAML is a bad place to keep logic.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Running `python scripts/foo.py` puts scripts/ on sys.path, not the project
# root, so project imports fail unless the package happens to be installed.
# CI installs it; a fresh clone does not. Bootstrap so both work.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

EXPECTED_HOURS = 48  # 2 forecast days x 24 hours


def main() -> int:
    from storage.warehouse import scalar, warehouse

    with warehouse() as con:
        raw = scalar(con, "SELECT count(*) FROM raw_weather_hourly")
        dupes = scalar(
            con,
            "SELECT count(*) FROM ("
            "  SELECT location_name, valid_at FROM raw_weather_hourly"
            "  GROUP BY 1, 2 HAVING count(*) > 1)",
        )

    if raw != EXPECTED_HOURS or dupes:
        print(
            f"IDEMPOTENCY BROKEN: {raw} rows (expected {EXPECTED_HOURS}), "
            f"{dupes} duplicate keys",
            file=sys.stderr,
        )
        return 1

    print(f"idempotency holds: {raw} rows, 0 duplicates after two runs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
