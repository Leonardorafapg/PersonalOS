from datetime import datetime

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PK, Base, Common, JSONType, UTCDateTime, utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(PK, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(300))
    # Bumping this invalidates every previously issued (non-expiring) token.
    token_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class UserPreferences(Common, Base):
    __tablename__ = "user_preferences"

    timezone: Mapped[str] = mapped_column(String(60), default="America/Sao_Paulo")
    data: Mapped[dict] = mapped_column(JSONType, default=dict)
