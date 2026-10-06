from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.crud import Draft, apply_fields, begin, compact, finish, get_live, item_ctx, only_set, soft_delete
from app.core.ctx import Ctx
from app.core.errors import validation
from app.core.ids import fmt
from app.core.timeutil import iso
from app.domains.audit import service as audit
from app.domains.projects.models import Project
from app.domains.tasks.models import Task

ET = "project"


class ProjectUpsert(BaseModel):
    """Create (no id) or update (id + version). Only the fields you send are changed."""

    id: str | None = Field(None, description="Existing project id (e.g. 'p3') to update")
    version: int | None = Field(None, description="Required when updating: the version from the last read")
    client_ref: str | None = Field(None, description="Your own stable key; makes creation idempotent")
    name: str | None = None
    description: str | None = None
    status: Literal["active", "paused", "done", "archived"] | None = None
    area: Literal["work", "personal", "study", "health"] | None = None
    color: str | None = None


def project_out(ctx: Ctx, p: Project, stats: dict | None = None) -> dict:
    out = {
        "id": fmt(ET, p.id),
        "name": p.name,
        "status": p.status,
        "area": p.area,
        "description": p.description,
        "color": p.color,
        "version": p.version,
        "created_by": p.created_by,
    }
    if stats:
        out.update(stats)
    return compact(out)


def _stats(ctx: Ctx, project_ids: list[int]) -> dict[int, dict]:
    if not project_ids:
        return {}
    today = ctx.today()
    rows = ctx.db.execute(
        select(
            Task.project_id,
            Task.status,
            func.count(Task.id),
            func.max(Task.updated_at),
        )
        .where(Task.user_id == ctx.user_id, Task.deleted_at.is_(None), Task.project_id.in_(project_ids))
        .group_by(Task.project_id, Task.status)
    ).all()
    out: dict[int, dict] = {pid: {"open_tasks": 0, "done_tasks": 0, "last_activity": None} for pid in project_ids}
    last: dict[int, object] = {}
    for pid, status, n, upd in rows:
        if status == "done":
            out[pid]["done_tasks"] += n
        elif status != "cancelled":
            out[pid]["open_tasks"] += n
        if upd and (pid not in last or upd > last[pid]):
            last[pid] = upd
    overdue = ctx.db.execute(
        select(Task.project_id, func.count(Task.id))
        .where(
            Task.user_id == ctx.user_id,
            Task.deleted_at.is_(None),
            Task.project_id.in_(project_ids),
            Task.status.in_(("inbox", "todo", "doing")),
            Task.due_date < today,
        )
        .group_by(Task.project_id)
    ).all()
    for pid, n in overdue:
        out[pid]["overdue_tasks"] = n
    for pid, upd in last.items():
        out[pid]["last_activity"] = iso(upd, ctx.tz)
    return out


def get_projects(ctx: Ctx, project_id: str | None = None, status: str | None = None) -> dict:
    if project_id:
        p = get_live(ctx, ET, Project, project_id)
        stats = _stats(ctx, [p.id])[p.id]
        from app.domains.tasks.service import list_tasks

        tasks = list_tasks(ctx, project_id=fmt(ET, p.id), limit=100)["tasks"]
        return {"project": {**project_out(ctx, p, stats), "tasks": tasks}}
    q = select(Project).where(Project.user_id == ctx.user_id, Project.deleted_at.is_(None))
    if status:
        q = q.where(Project.status == status)
    else:
        q = q.where(Project.status != "archived")
    projects = ctx.db.scalars(q.order_by(Project.name)).all()
    stats = _stats(ctx, [p.id for p in projects])
    return {"projects": [project_out(ctx, p, stats[p.id]) for p in projects]}


def save_projects(ctx: Ctx, items: list[ProjectUpsert]) -> dict:
    results = []
    for i, item in enumerate(items):
        with item_ctx(i):
            d = begin(
                ctx, ET, Project, id=item.id, version=item.version, client_ref=item.client_ref,
                defaults={"status": "active", "area": "work"},
            )
            vals = only_set(item, "name", "description", "status", "area", "color")
            for k in ("name", "status", "area"):
                if k in vals and vals[k] is None:
                    raise validation(f"{k} cannot be null", k)
            if "name" in vals:
                vals["name"] = vals["name"].strip()
                if not vals["name"]:
                    raise validation("name cannot be empty", "name")
            if d.created and not vals.get("name"):
                raise validation("name is required to create a project", "name")
            apply_fields(d.obj, vals)
            action = finish(ctx, d, ET, d.obj.name)
            results.append({"action": action, "project": project_out(ctx, d.obj)})
    return {"results": results}


def delete_project(ctx: Ctx, p: Project) -> dict:
    """Soft delete. Tasks stay but are detached from the project (recorded, so undo restores them)."""
    tasks = ctx.db.scalars(
        select(Task).where(Task.user_id == ctx.user_id, Task.project_id == p.id, Task.deleted_at.is_(None))
    ).all()
    for t in tasks:
        d = Draft(t, False, audit.snapshot(t))
        t.project_id = None
        finish(ctx, d, "task", t.title)
    soft_delete(ctx, ET, p, p.name)
    return {"detached_tasks": len(tasks)}
