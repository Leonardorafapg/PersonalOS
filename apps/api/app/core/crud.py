"""Generic helpers shared by every domain service: load, upsert (begin/finish), soft delete."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.core.ctx import Ctx
from app.core.errors import AppError, not_found, validation
from app.core.ids import fmt, parse
from app.domains.audit import service as audit


def touch(ctx: Ctx, obj) -> None:
    obj.version = (obj.version or 1) + 1
    obj.updated_at = ctx.now()
    obj.updated_by = ctx.actor


def get_live(ctx: Ctx, entity_type: str, Model, ident: str | int | None, field: str = "id"):
    pk = parse(entity_type, ident, field)
    obj = ctx.db.get(Model, pk)
    if obj is None or obj.user_id != ctx.user_id or obj.deleted_at is not None:
        raise not_found(entity_type.replace("_", " "), fmt(entity_type, pk))
    return obj


def find_by_ref(ctx: Ctx, Model, client_ref: str):
    return ctx.db.scalars(
        select(Model).where(
            Model.user_id == ctx.user_id, Model.client_ref == client_ref, Model.deleted_at.is_(None)
        )
    ).first()


@dataclass
class Draft:
    obj: Any
    created: bool
    before: dict | None


def begin(
    ctx: Ctx,
    entity_type: str,
    Model,
    *,
    id: str | int | None = None,
    version: int | None = None,
    client_ref: str | None = None,
    defaults: dict | None = None,
) -> Draft:
    obj = None
    if id is not None:
        obj = get_live(ctx, entity_type, Model, id)
        if version is None:
            raise validation(
                f"'version' is required to update {id}. Use the version returned by the last read.", "version"
            )
        if obj.version != version:
            raise AppError(
                "STALE_VERSION",
                f"{id} changed since you read it (you sent v{version}, current is v{obj.version}). "
                "Re-read it and retry.",
                details={"id": str(id), "current_version": obj.version},
            )
    elif client_ref:
        obj = find_by_ref(ctx, Model, client_ref)
    if obj is not None:
        return Draft(obj, False, audit.snapshot(obj))
    obj = Model(
        user_id=ctx.user_id, created_by=ctx.actor, updated_by=ctx.actor, client_ref=client_ref, **(defaults or {})
    )
    return Draft(obj, True, None)


def finish(ctx: Ctx, d: Draft, entity_type: str, label: str) -> str:
    """Persist a draft and write the audit record. Returns created | updated | unchanged."""
    if d.created:
        ctx.db.add(d.obj)
        ctx.db.flush()
        audit.created(ctx, entity_type, d.obj, label)
        return "created"
    changed = audit.diff_keys(d.before, audit.snapshot(d.obj))
    if not changed:
        return "unchanged"
    touch(ctx, d.obj)
    ctx.db.flush()
    audit.updated(ctx, entity_type, d.obj, d.before, label, changed)
    return "updated"


def soft_delete(ctx: Ctx, entity_type: str, obj, label: str) -> None:
    before = audit.snapshot(obj)
    obj.deleted_at = ctx.now()
    touch(ctx, obj)
    ctx.db.flush()
    audit.deleted(ctx, entity_type, obj, before, label)


def apply_fields(obj, values: dict[str, Any]) -> None:
    for k, v in values.items():
        setattr(obj, k, v)


def only_set(item, *names: str) -> dict[str, Any]:
    """Return {name: value} for the fields the caller explicitly sent (even if null)."""
    sent = item.model_fields_set
    return {n: getattr(item, n) for n in names if n in sent}


def compact(d: dict) -> dict:
    """Drop None / False / empty containers so responses stay small."""
    return {k: v for k, v in d.items() if v is not None and v is not False and v != [] and v != {}}


from contextlib import contextmanager  # noqa: E402


@contextmanager
def item_ctx(idx: int):
    """Annotate errors raised while processing items[idx] so the caller knows which item failed."""
    try:
        yield
    except AppError as e:
        e.details = {**(e.details or {}), "item_index": idx}
        e.message = f"items[{idx}]: {e.message}"
        e.args = (e.message,)
        raise
