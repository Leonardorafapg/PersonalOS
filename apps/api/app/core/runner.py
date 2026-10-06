"""Runs one operation (REST call or MCP tool) in its own transaction and wraps the outcome in the standard envelope."""

from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core import db as dbmod
from app.core.ctx import Ctx
from app.core.errors import AppError
from app.core.timeutil import iso

log = logging.getLogger("personal_os")


def _mask(obj: Any, new_ids: set[str]) -> Any:
    """In a dry run, rows were only provisionally created: hide their ids."""
    if isinstance(obj, str):
        return "(new)" if obj in new_ids else obj
    if isinstance(obj, list):
        return [_mask(x, new_ids) for x in obj]
    if isinstance(obj, dict):
        return {k: _mask(v, new_ids) for k, v in obj.items()}
    return obj


def run(
    user_id: int,
    actor: str,
    channel: str,
    tool: str,
    fn: Callable[[Ctx], Any],
    *,
    write: bool,
    dry_run: bool = False,
) -> tuple[int, dict]:
    """Returns (http_status, envelope)."""
    with dbmod.SessionLocal() as db:
        ctx = Ctx(db=db, user_id=user_id, actor=actor, channel=channel, tool=tool, dry_run=dry_run)
        try:
            if write and db.bind.dialect.name == "postgresql":
                # Serialize writers per user: removes check-then-write races on the schedule.
                db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": user_id})
            data = fn(ctx)
            if write and not dry_run:
                db.commit()
            else:
                db.rollback()
            meta: dict[str, Any] = {"now": iso(ctx.now(), ctx.tz) if ctx._prefs_cache else None}
            if write:
                meta["batch_id"] = ctx.batch_id
            if dry_run:
                meta["dry_run"] = True
                data = _mask(data, ctx.new_ids)
            env: dict[str, Any] = {"ok": True, "data": data, "meta": meta}
            if ctx.warnings:
                env["warnings"] = _mask(ctx.warnings, ctx.new_ids) if dry_run else ctx.warnings
            return 200, env
        except AppError as err:
            db.rollback()
            if write:
                try:
                    from app.domains.audit.service import log_rejection

                    log_rejection(user_id, actor, channel, tool, ctx.batch_id, err)
                except Exception:  # noqa: BLE001
                    log.exception("could not log rejected operation")
            env = {"ok": False, "error": err.to_dict(), "meta": {"batch_id": ctx.batch_id} if write else {}}
            return err.http_status, env
        except SQLAlchemyError as exc:
            db.rollback()
            log.exception("database error in %s", tool)
            err = AppError("INTERNAL", "Database error; nothing was changed.", details={"type": type(exc).__name__})
            return 500, {"ok": False, "error": err.to_dict(), "meta": {}}
        except Exception:  # noqa: BLE001
            db.rollback()
            log.exception("unexpected error in %s", tool)
            err = AppError("INTERNAL", "Unexpected error; nothing was changed.")
            return 500, {"ok": False, "error": err.to_dict(), "meta": {}}
