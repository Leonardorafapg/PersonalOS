"""Operation log + undo. Every mutation is recorded in the same transaction as the change."""

from __future__ import annotations

import copy
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select

from app.core.ctx import Ctx
from app.core.errors import AppError, not_found, validation
from app.core.ids import PREFIX, fmt
from app.domains.audit.models import OperationLog

# entity_type -> SQLAlchemy model, filled in by app.registry
MODELS: dict[str, type] = {}

# Bookkeeping columns that never count as a "change".
META = {"version", "updated_at", "updated_by"}
# Columns restored verbatim on undo (everything else is identity/ownership).
NO_RESTORE = {"id", "user_id", "created_at", "created_by", "version", "updated_at", "updated_by"}


def _json_safe(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return copy.deepcopy(v)
    if isinstance(v, datetime):
        return v.astimezone(timezone.utc).isoformat()
    if isinstance(v, (date, time)):
        return v.isoformat()
    return v


def snapshot(obj) -> dict:
    return {c.key: _json_safe(getattr(obj, c.key)) for c in obj.__table__.columns}


def _from_json(col, v):
    if v is None:
        return None
    impl = getattr(col.type, "impl", col.type)  # unwrap TypeDecorator (UTCDateTime)
    if isinstance(impl, sa.DateTime):
        return datetime.fromisoformat(v)
    if isinstance(impl, sa.Date):
        return date.fromisoformat(v)
    return v


def restore(obj, snap: dict) -> None:
    for c in obj.__table__.columns:
        if c.key in NO_RESTORE or c.key not in snap:
            continue
        setattr(obj, c.key, _from_json(c, snap[c.key]))


def diff_keys(before: dict, after: dict) -> list[str]:
    return [k for k in after if k not in META and before.get(k) != after.get(k)]


def _record(ctx: Ctx, entity_type: str | None, entity_id: int | None, action: str, summary: str,
            before: dict | None, after: dict | None) -> None:
    ctx.seq += 1
    ctx.db.add(
        OperationLog(
            user_id=ctx.user_id,
            batch_id=ctx.batch_id,
            seq=ctx.seq,
            ts=ctx.now(),
            actor=ctx.actor,
            channel=ctx.channel,
            tool=ctx.tool,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            summary=summary[:300],
            before=before,
            after=after,
            result="ok",
        )
    )


def created(ctx: Ctx, entity_type: str, obj, label: str) -> None:
    ctx.new_ids.add(fmt(entity_type, obj.id))
    _record(ctx, entity_type, obj.id, "create", label, None, snapshot(obj))


def updated(ctx: Ctx, entity_type: str, obj, before: dict, label: str, changed: list[str]) -> None:
    summary = f"{label} [{', '.join(changed)}]" if changed else label
    _record(ctx, entity_type, obj.id, "update", summary, before, snapshot(obj))


def deleted(ctx: Ctx, entity_type: str, obj, before: dict, label: str) -> None:
    _record(ctx, entity_type, obj.id, "delete", label, before, snapshot(obj))


def restored(ctx: Ctx, entity_type: str, obj, before: dict, label: str) -> None:
    _record(ctx, entity_type, obj.id, "restore", label, before, snapshot(obj))


def log_rejection(user_id: int, actor: str, channel: str, tool: str, batch_id: str, err: AppError) -> None:
    """Rejected operations are logged in their own transaction (the main one was rolled back)."""
    from app.core.db import SessionLocal

    with SessionLocal() as db:
        db.add(
            OperationLog(
                user_id=user_id, batch_id=batch_id, seq=0, ts=_now(), actor=actor, channel=channel, tool=tool,
                action="reject", summary=err.message[:300], result="rejected", error_code=err.code,
                error_message=err.message,
            )
        )
        db.commit()


def _now() -> datetime:
    from app.core import clock

    return clock.now()


# -- reading ----------------------------------------------------------------

def list_batches(
    ctx: Ctx,
    *,
    since_hours: int = 24,
    actor: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    batch_id: str | None = None,
    include_rejected: bool = True,
    limit: int = 30,
) -> dict:
    from app.core.ids import parse

    q = select(OperationLog).where(OperationLog.user_id == ctx.user_id)
    if batch_id:
        q = q.where(OperationLog.batch_id == batch_id)
    else:
        q = q.where(OperationLog.ts >= ctx.now() - timedelta(hours=since_hours))
    if actor:
        q = q.where(OperationLog.actor == actor)
    if entity_type:
        if entity_type not in PREFIX:
            raise validation(f"Unknown entity_type '{entity_type}'. Use one of {sorted(PREFIX)}", "entity_type")
        q = q.where(OperationLog.entity_type == entity_type)
    if entity_id:
        et = entity_type
        if et is None:
            raise validation("entity_type is required together with entity_id", "entity_type")
        q = q.where(OperationLog.entity_id == parse(et, entity_id, "entity_id"))
    if not include_rejected:
        q = q.where(OperationLog.result == "ok")
    rows = ctx.db.scalars(q.order_by(OperationLog.ts.desc(), OperationLog.id.desc()).limit(limit * 20)).all()

    batches: dict[str, dict] = {}
    for r in rows:
        b = batches.get(r.batch_id)
        if b is None:
            if len(batches) >= limit:
                continue
            b = batches[r.batch_id] = {
                "batch_id": r.batch_id,
                "ts": r.ts.astimezone(ctx.tz).isoformat(timespec="seconds"),
                "actor": r.actor,
                "channel": r.channel,
                "tool": r.tool,
                "result": r.result,
                "undone_by": r.undone_by,
                "changes": [],
            }
        change = {
            "action": r.action,
            "entity": fmt(r.entity_type, r.entity_id) if r.entity_type and r.entity_id else None,
            "summary": r.summary,
        }
        if r.error_code:
            change["error"] = r.error_code
        b["changes"].append(change)
    out = list(batches.values())
    for b in out:
        b["changes"].reverse()  # chronological inside a batch
        b["count"] = len(b["changes"])
    return {"batches": out, "count": len(out)}


# -- undo -------------------------------------------------------------------

def undo_batch(ctx: Ctx, batch_id: str) -> dict:
    ops = ctx.db.scalars(
        select(OperationLog)
        .where(
            OperationLog.user_id == ctx.user_id,
            OperationLog.batch_id == batch_id,
            OperationLog.result == "ok",
            OperationLog.action.in_(("create", "update", "delete", "restore")),
        )
        .order_by(OperationLog.seq.desc(), OperationLog.id.desc())
    ).all()
    if not ops:
        raise not_found("operation batch", batch_id)
    if any(o.undone_by for o in ops):
        raise AppError("UNDO_NOT_POSSIBLE", f"Batch {batch_id} was already undone")
    if batch_id == ctx.batch_id:
        raise validation("Cannot undo the current batch")

    # 1) validate: every entity must still be in the state this batch left it in
    cur: dict[tuple[str, int], int] = {}
    objs: dict[tuple[str, int], Any] = {}
    for op in ops:
        key = (op.entity_type, op.entity_id)
        Model = MODELS[op.entity_type]
        if key not in objs:
            objs[key] = ctx.db.get(Model, op.entity_id)
            if objs[key] is None or objs[key].user_id != ctx.user_id:
                raise AppError("UNDO_NOT_POSSIBLE", f"{fmt(*key)} no longer exists")
            cur[key] = objs[key].version
        if op.after["version"] != cur[key]:
            raise AppError(
                "UNDO_NOT_POSSIBLE",
                f"{fmt(*key)} was changed after this batch (now v{cur[key]}, batch left v{op.after['version']}). "
                "Undo it manually or undo the later batch first.",
                details={"entity": fmt(*key)},
            )
        cur[key] = op.before["version"] if op.before else -1

    # 2) apply in reverse order
    from app.core.crud import touch  # local import to avoid a cycle

    reverted = []
    for op in ops:
        obj = objs[(op.entity_type, op.entity_id)]
        before_now = snapshot(obj)
        label = (op.summary or "").split(" [")[0]
        if op.action == "create":
            obj.deleted_at = ctx.now()
            touch(ctx, obj)
            ctx.db.flush()
            deleted(ctx, op.entity_type, obj, before_now, f"↩ {label}")
        elif op.action in ("update", "delete", "restore"):
            restore(obj, op.before)
            touch(ctx, obj)
            ctx.db.flush()
            fn = restored if op.action == "delete" else updated
            if op.action == "delete":
                fn(ctx, op.entity_type, obj, before_now, f"↩ {label}")
            else:
                fn(ctx, op.entity_type, obj, before_now, f"↩ {label}", [])
        reverted.append({"entity": fmt(op.entity_type, op.entity_id), "was": op.action, "label": label})
    if not ctx.dry_run:
        for op in ops:
            op.undone_by = ctx.batch_id
    return {"undone_batch": batch_id, "reverted": reverted}
