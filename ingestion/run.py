"""
Ingestion entrypoint.

    python -m ingestion.run weather            # live API
    python -m ingestion.run weather --offline  # replay the fixture

Phase 1 is deliberately a plain CLI. Phase 3 wraps these same functions in
Dagster assets — the business logic should not have to change when you add
an orchestrator, and if it does, the boundary was drawn in the wrong place.
"""

from __future__ import annotations

import argparse
import sys
import uuid

from config.settings import LOCATION
from ingestion.sources import weather
from storage import warehouse as wh


def run_weather(offline: bool = False) -> int:
    run_id = f"weather-{wh.utcnow():%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"

    with wh.warehouse() as con:
        wh.start_run(con, run_id, "weather")
        try:
            payload = weather.load_fixture() if offline else weather.fetch()
            weather.archive(payload, run_id)
            rows = weather.normalize(payload, LOCATION.name)
            written = wh.merge_weather_hourly(con, rows, run_id)
            wh.finish_run(con, run_id, "success", written)
            print(f"[{run_id}] ok — {written} hourly rows merged")
            return written
        except Exception as exc:
            wh.finish_run(con, run_id, "failed", 0, str(exc)[:500])
            print(f"[{run_id}] FAILED — {exc}", file=sys.stderr)
            raise


SOURCES = {"weather": run_weather}


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest a source.")
    parser.add_argument("source", choices=sorted(SOURCES))
    parser.add_argument(
        "--offline",
        action="store_true",
        help="replay the local fixture instead of calling the API",
    )
    args = parser.parse_args()
    SOURCES[args.source](offline=args.offline)


if __name__ == "__main__":
    main()
