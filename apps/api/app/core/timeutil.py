from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.errors import validation

UTC = timezone.utc
WEEKDAYS_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def get_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except Exception as exc:  # noqa: BLE001
        raise validation(f"Unknown timezone '{name}'", "timezone") from exc


def to_utc(dt: datetime, tz: ZoneInfo) -> datetime:
    """Naive datetimes are interpreted as wall-clock time in the user's timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt.astimezone(UTC)


def local(dt: datetime, tz: ZoneInfo) -> datetime:
    return dt.astimezone(tz)


def iso(dt: datetime | None, tz: ZoneInfo) -> str | None:
    """ISO string in the user's timezone, without seconds (e.g. 2026-10-07T08:00-03:00)."""
    if dt is None:
        return None
    return dt.astimezone(tz).isoformat(timespec="minutes")


def day_bounds(d: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=tz).astimezone(UTC)
    end = datetime.combine(d + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC)
    return start, end


def local_midnight(d: date, tz: ZoneInfo) -> datetime:
    return datetime.combine(d, time.min, tzinfo=tz).astimezone(UTC)


def parse_hhmm(value: str) -> time:
    try:
        h, m = value.split(":")
        return time(int(h), int(m))
    except Exception as exc:  # noqa: BLE001
        raise validation(f"Invalid time '{value}', expected HH:MM") from exc


def minutes_between(a: datetime, b: datetime) -> int:
    return int((b - a).total_seconds() // 60)


def week_start(d: date) -> date:
    """Monday of the week containing d."""
    return d - timedelta(days=d.weekday())


def weekday_name(d: date) -> str:
    return WEEKDAYS_PT[d.weekday()]
