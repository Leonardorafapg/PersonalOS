"""Public ids are short, typed strings (t42, c7, p3...). The database stores plain integers."""

import re

PREFIX = {
    "task": "t",
    "calendar_entry": "c",
    "project": "p",
    "study_topic": "s",
    "study_session": "ss",
    "routine": "ro",
    "workout_session": "ws",
    "daily_plan": "dp",
    "preferences": "pref",
}

_RE = re.compile(r"^([a-z]+)(\d+)$")


def fmt(entity: str, ident: int | None) -> str | None:
    if ident is None:
        return None
    return f"{PREFIX[entity]}{ident}"


def parse(entity: str, value: str | int | None, field: str = "id") -> int:
    """Accept "t42", "42" or 42 for a task id. Raises ValueError on a wrong type or malformed value."""
    from app.core.errors import validation

    if value is None:
        raise validation(f"{field} is required", field)
    if isinstance(value, int):
        return value
    s = str(value).strip().lower()
    if s.isdigit():
        return int(s)
    m = _RE.match(s)
    if not m:
        raise validation(f"Invalid id '{value}'. Expected something like '{PREFIX[entity]}12'", field)
    if m.group(1) != PREFIX[entity]:
        raise validation(
            f"Id '{value}' is not a {entity} id (expected prefix '{PREFIX[entity]}')", field
        )
    return int(m.group(2))
