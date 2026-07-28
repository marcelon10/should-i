"""
Time handling, in one place.

This module exists because ruff's DTZ rules caught a real bug rather than a
style nit. `date.today()` returns the *server's* today. Run the pipeline in a
GitHub Actions runner (UTC) at 23:30 Lisbon time and it would ask the mart for
tomorrow's date and report "no data" — a failure that only appears at night,
only in CI, and only sometimes. That class of bug is miserable to chase.

Rules for the whole project:
  * storage and bookkeeping timestamps -> UTC (`utcnow`)
  * anything a human reads or that keys a calendar day -> LOCATION.timezone
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from config.settings import LOCATION


def tz() -> ZoneInfo:
    """The configured local timezone."""
    return ZoneInfo(LOCATION.timezone)


def utcnow() -> datetime:
    """Now in UTC, naive — DuckDB TIMESTAMP columns are tz-less by design."""
    return datetime.now(UTC).replace(tzinfo=None)


def local_now() -> datetime:
    """Now, where the user actually is."""
    return datetime.now(tz())


def local_today() -> date:
    """Today, where the user actually is. Never use `date.today()`."""
    return local_now().date()
