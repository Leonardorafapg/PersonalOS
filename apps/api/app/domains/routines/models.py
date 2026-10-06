from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Common, JSONType


class Routine(Common, Base):
    """A cadence template (e.g. Jiu-Jitsu 3x/week). Concrete sessions become calendar entries."""

    __tablename__ = "routines"

    kind: Mapped[str] = mapped_column(String(12), default="training")
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_per_week: Mapped[int] = mapped_column(Integer, default=1)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    preferred_days: Mapped[list] = mapped_column(JSONType, default=list)  # 0=Mon .. 6=Sun
    preferred_start: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM
    preferred_end: Mapped[str | None] = mapped_column(String(5), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Customizable exercise plan: [{key, name, exercises: [{key, name, sets, reps, load, rest_seconds, notes}]}]
    workouts: Mapped[list] = mapped_column(JSONType, default=list)


class WorkoutSession(Common, Base):
    """One performed (or in-progress) workout. Exercises are a snapshot of the template, so history never
    changes when the plan is edited. Each exercise is done = true | false | null (pending)."""

    __tablename__ = "workout_sessions"

    routine_id: Mapped[int] = mapped_column(ForeignKey("routines.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    workout_key: Mapped[str | None] = mapped_column(String(30), nullable=True)
    workout_name: Mapped[str] = mapped_column(String(120), default="")
    entry_id: Mapped[int | None] = mapped_column(ForeignKey("calendar_entries.id"), nullable=True, index=True)
    exercises: Mapped[list] = mapped_column(JSONType, default=list)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    effort: Mapped[int | None] = mapped_column(Integer, nullable=True)  # perceived effort 1-10
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
