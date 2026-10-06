from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core import clock
from app.core.timeutil import get_tz

if TYPE_CHECKING:  # pragma: no cover
    from app.domains.identity.schemas import Preferences


def new_batch_id() -> str:
    return "op_" + uuid.uuid4().hex[:10]


@dataclass
class Ctx:
    """Everything a service needs to know about the current operation."""

    db: Session
    user_id: int
    actor: str  # manual | claude | system
    channel: str  # ui | mcp | api
    tool: str
    batch_id: str = field(default_factory=new_batch_id)
    dry_run: bool = False
    warnings: list[dict] = field(default_factory=list)
    seq: int = 0
    new_ids: set = field(default_factory=set)
    _prefs_cache: tuple | None = None

    # -- mode ---------------------------------------------------------------
    @property
    def strict(self) -> bool:
        """Strict mode (Claude / system): conflicts, past dates and fixed events are protected.
        Manual edits from the UI only produce warnings."""
        return self.actor != "manual"

    # -- time ---------------------------------------------------------------
    def now(self) -> datetime:
        return clock.now()

    @property
    def tz(self) -> ZoneInfo:
        return get_tz(self.prefs_row().timezone)

    def today(self) -> date:
        return self.now().astimezone(self.tz).date()

    # -- preferences --------------------------------------------------------
    def prefs_row(self):
        from app.domains.identity import service as identity

        return identity.get_prefs_row(self)

    @property
    def prefs(self) -> "Preferences":
        from app.domains.identity import service as identity

        return identity.get_prefs(self)

    def invalidate_prefs(self) -> None:
        self._prefs_cache = None

    # -- warnings -----------------------------------------------------------
    def warn(self, code: str, message: str, **extra) -> None:
        self.warnings.append({"code": code, "message": message, **extra})
