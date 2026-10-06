import re

from pydantic import BaseModel, Field, field_validator

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _check_hhmm(v: str | None) -> str | None:
    if v is not None and not HHMM.match(v):
        raise ValueError("expected HH:MM (24h)")
    return v


class Meal(BaseModel):
    name: str
    start: str
    end: str

    _v = field_validator("start", "end")(_check_hhmm)


class Preferences(BaseModel):
    """What I (Claude) need to know to plan well. Stored as JSON next to the timezone."""

    wake_time: str = "07:00"
    sleep_time: str = "23:00"
    work_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], description="0=Mon .. 6=Sun")
    work_start: str = "09:00"
    work_end: str = "18:00"
    meals: list[Meal] = Field(default_factory=lambda: [Meal(name="Almoço", start="12:00", end="13:00")])
    planning_rules: list[str] = Field(
        default_factory=list, description="Free-text rules, e.g. 'Não estudar depois das 22h'."
    )
    context_notes: str = Field("", description="Free-text personal context useful when planning.")
    min_free_window_minutes: int = Field(15, ge=5, le=120)

    _v = field_validator("wake_time", "sleep_time", "work_start", "work_end")(_check_hhmm)

    @field_validator("work_days")
    @classmethod
    def _days(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("days must be 0..6")
        return sorted(set(v))


class PreferencesPatch(BaseModel):
    """Only the fields you send are changed. List fields are replaced as a whole."""

    version: int | None = None
    timezone: str | None = None
    wake_time: str | None = None
    sleep_time: str | None = None
    work_days: list[int] | None = None
    work_start: str | None = None
    work_end: str | None = None
    meals: list[Meal] | None = None
    planning_rules: list[str] | None = None
    context_notes: str | None = None
    min_free_window_minutes: int | None = Field(None, ge=5, le=120)

    _v = field_validator("wake_time", "sleep_time", "work_start", "work_end")(_check_hhmm)


class LoginIn(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)
