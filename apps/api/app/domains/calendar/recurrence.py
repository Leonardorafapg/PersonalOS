"""RRULE helpers. Rules are evaluated in the user's wall-clock time so 19:00 stays 19:00 across DST."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr

from app.core.errors import validation
from app.core.timeutil import UTC

MAX_OCCURRENCES = 400


def normalize_rrule(text: str) -> str:
    text = text.strip()
    if text.upper().startswith("RRULE:"):
        text = text[6:]
    if "DTSTART" in text.upper() or "\n" in text:
        raise validation("rrule must be a bare RRULE (no DTSTART); the entry's start is the first occurrence", "rrule")
    if "FREQ=" not in text.upper():
        raise validation("rrule needs FREQ, e.g. FREQ=WEEKLY;BYDAY=MO,WE", "rrule")
    # UNTIL is evaluated in naive local time: drop a trailing Z and complete date-only values.
    text = re.sub(r"(UNTIL=\d{8}T\d{6})Z", r"\1", text, flags=re.I)
    text = re.sub(r"(UNTIL=\d{8})(?![\dT])", r"\1T235959", text, flags=re.I)
    try:
        rrulestr(text, dtstart=datetime(2000, 1, 1))
    except Exception as exc:  # noqa: BLE001
        raise validation(f"Invalid rrule: {exc}", "rrule") from exc
    return text.upper()


def expand(
    rrule: str,
    start: datetime,
    end: datetime,
    tz: ZoneInfo,
    window_start: datetime,
    window_end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Occurrences (UTC start, UTC end) overlapping [window_start, window_end)."""
    dur = end - start
    naive_start = start.astimezone(tz).replace(tzinfo=None)
    rule = rrulestr(rrule, dtstart=naive_start)
    lo = window_start.astimezone(tz).replace(tzinfo=None) - dur
    hi = window_end.astimezone(tz).replace(tzinfo=None)
    out: list[tuple[datetime, datetime]] = []
    for dt in rule.between(lo, hi, inc=True):
        s = dt.replace(tzinfo=tz).astimezone(UTC)
        e = s + dur
        if s < window_end and e > window_start:
            out.append((s, e))
        if len(out) >= MAX_OCCURRENCES:
            break
    return out


def is_occurrence(rrule: str, start: datetime, end: datetime, tz: ZoneInfo, candidate: datetime) -> bool:
    for s, _ in expand(rrule, start, end, tz, candidate - timedelta(minutes=1), candidate + timedelta(minutes=1)):
        if s == candidate:
            return True
    return False
