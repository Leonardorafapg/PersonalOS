"""Single source of 'now'. Tests can freeze it."""

from datetime import datetime, timezone

_frozen: datetime | None = None


def now() -> datetime:
    return _frozen or datetime.now(timezone.utc)


def freeze(dt: datetime | None) -> None:
    global _frozen
    _frozen = dt
