from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Common, UTCDateTime


class CalendarEntry(Common, Base):
    """Fixed events and flexible planned blocks live in the same table (`mobility`)."""

    __tablename__ = "calendar_entries"

    title: Mapped[str] = mapped_column(String(300))
    mobility: Mapped[str] = mapped_column(String(10), default="fixed")  # fixed | flexible
    category: Mapped[str] = mapped_column(String(20), default="other")
    start_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    end_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(10), default="planned")  # planned|done|skipped|cancelled
    skip_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True, index=True)
    study_topic_id: Mapped[int | None] = mapped_column(ForeignKey("study_topics.id"), nullable=True, index=True)
    routine_id: Mapped[int | None] = mapped_column(ForeignKey("routines.id"), nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    # Recurrence: master rows carry an RRULE; overriding a single occurrence creates a child
    # row (series_id + original_start). A cancelled child removes that occurrence.
    rrule: Mapped[str | None] = mapped_column(String(300), nullable=True)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("calendar_entries.id"), nullable=True, index=True)
    original_start: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
