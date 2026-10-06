from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, JSONType, UTCDateTime, utcnow


class OperationLog(Base):
    __tablename__ = "operation_log"

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    batch_id: Mapped[str] = mapped_column(String(24), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(10))  # manual | claude | system
    channel: Mapped[str] = mapped_column(String(10))  # ui | mcp | api
    tool: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(12))  # create | update | delete | restore | reject
    summary: Mapped[str] = mapped_column(String(300), default="")
    before: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    result: Mapped[str] = mapped_column(String(10), default="ok")  # ok | rejected
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    undone_by: Mapped[str | None] = mapped_column(String(24), nullable=True)
