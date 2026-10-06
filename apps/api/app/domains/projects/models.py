from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Common


class Project(Common, Base):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="active")  # active|paused|done|archived
    area: Mapped[str] = mapped_column(String(12), default="work")  # work|personal|study|health
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
