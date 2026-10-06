from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Common, JSONType


class StudyTopic(Common, Base):
    """Roadmap node. Roots (kind=area) group topics; any node may have children."""

    __tablename__ = "study_topics"

    parent_id: Mapped[int | None] = mapped_column(ForeignKey("study_topics.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(8), default="topic")  # area | topic
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="not_started")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resources: Mapped[list] = mapped_column(JSONType, default=list)
    prerequisite_ids: Mapped[list] = mapped_column(JSONType, default=list)


class StudySession(Common, Base):
    __tablename__ = "study_sessions"

    topic_id: Mapped[int] = mapped_column(ForeignKey("study_topics.id"), index=True)
    session_date: Mapped[date] = mapped_column(Date, index=True)
    minutes: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    entry_id: Mapped[int | None] = mapped_column(ForeignKey("calendar_entries.id"), nullable=True)
