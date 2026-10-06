from datetime import date

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Common


class DailyPlan(Common, Base):
    """Thin per-day metadata. The day's content is the calendar entries of that date."""

    __tablename__ = "daily_plans"

    plan_date: Mapped[date] = mapped_column(Date, index=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="active")  # draft | active
