from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import case, or_, select

from app.core.crud import Draft, apply_fields, begin, compact, finish, get_live, item_ctx, only_set, soft_delete
from app.core.ctx import Ctx
from app.core.errors import validation
from app.core.ids import fmt, parse
from app.core.timeutil import iso
from app.domains.audit import service as audit
from app.domains.calendar.models import CalendarEntry
from app.domains.projects.models import Project
from app.domains.tasks.models import Task

ET = "task"
OPEN = ("inbox", "todo", "doing")
PRIORITY_RANK = case(
    (Task.priority == "urgent", 0), (Task.priority == "high", 1), (Task.priority == "medium", 2), else_=3
)


class TaskUpsert(BaseModel):
    """Create (no id) or update (id + version). Only the fields you send are changed; send null to clear."""

    id: str | None = Field(None, description="Existing task id (e.g. 't42') to update")
    version: int | None = Field(None, description="Required when updating: the version from the last read")
    client_ref: str | None = Field(None, description="Your own stable key; makes creation idempotent")
    title: str | None = None
    description: str | None = None
    status: Literal["inbox", "todo", "doing", "done", "cancelled"] | None = Field(
        None, description="Set 'done' to complete. Reopen by setting 'todo'."
    )
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    due_date: date | None = Field(None, description="Deadline (date only)")
    do_date: date | None = Field(None, description="The day you intend to do it (not the deadline)")
    estimated_minutes: int | None = Field(None, ge=1, le=1440)
    project_id: str | None = Field(None, description="Project id like 'p3'; null detaches")
    parent_id: str | None = Field(None, description="Parent task id for a subtask (one level only)")
    category: str | None = None
    notes: str | None = None


def _scheduled_map(ctx: Ctx, task_ids: list[int]) -> dict[int, list[dict]]:
    if not task_ids:
        return {}
    rows = ctx.db.scalars(
        select(CalendarEntry)
        .where(
            CalendarEntry.user_id == ctx.user_id,
            CalendarEntry.deleted_at.is_(None),
            CalendarEntry.task_id.in_(task_ids),
            CalendarEntry.status == "planned",
            CalendarEntry.end_at >= ctx.now(),
        )
        .order_by(CalendarEntry.start_at)
    ).all()
    out: dict[int, list[dict]] = {}
    for e in rows:
        out.setdefault(e.task_id, []).append(
            {"id": fmt("calendar_entry", e.id), "start": iso(e.start_at, ctx.tz), "end": iso(e.end_at, ctx.tz)}
        )
    return out


def tasks_out(ctx: Ctx, tasks: list[Task], *, detail: bool = True) -> list[dict]:
    today = ctx.today()
    pids = {t.project_id for t in tasks if t.project_id}
    names = {}
    if pids:
        names = {p.id: p.name for p in ctx.db.scalars(select(Project).where(Project.id.in_(pids)))}
    sched = _scheduled_map(ctx, [t.id for t in tasks])
    out = []
    for t in tasks:
        d = {
            "id": fmt(ET, t.id),
            "title": t.title,
            "status": t.status,
            "priority": t.priority,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "do_date": t.do_date.isoformat() if t.do_date else None,
            "estimated_minutes": t.estimated_minutes,
            "project_id": fmt("project", t.project_id),
            "project_name": names.get(t.project_id),
            "parent_id": fmt(ET, t.parent_id),
            "category": t.category,
            "overdue": bool(t.due_date and t.due_date < today and t.status in OPEN),
            "scheduled": sched.get(t.id),
            "version": t.version,
            "created_by": t.created_by,
        }
        if detail:
            d["description"] = t.description
            d["notes"] = t.notes
            d["completed_at"] = iso(t.completed_at, ctx.tz) if t.completed_at else None
            d["created_at"] = iso(t.created_at, ctx.tz)
        out.append(compact(d))
    return out


def list_tasks(
    ctx: Ctx,
    *,
    ids: list[str] | None = None,
    status: list[str] | None = None,
    project_id: str | None = None,
    parent_id: str | None = None,
    due_before: date | None = None,
    due_on: date | None = None,
    do_date: date | None = None,
    overdue: bool | None = None,
    no_project: bool | None = None,
    q: str | None = None,
    include_done_since: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    query = select(Task).where(Task.user_id == ctx.user_id, Task.deleted_at.is_(None))
    if ids:
        query = query.where(Task.id.in_([parse(ET, i, "ids") for i in ids]))
    else:
        statuses = list(status) if status else list(OPEN)
        cond = Task.status.in_(statuses)
        if include_done_since:
            from datetime import datetime, time

            cutoff = datetime.combine(include_done_since, time.min, tzinfo=ctx.tz)
            cond = or_(cond, (Task.status == "done") & (Task.completed_at >= cutoff))
        query = query.where(cond)
    if project_id:
        query = query.where(Task.project_id == parse("project", project_id, "project_id"))
    if no_project:
        query = query.where(Task.project_id.is_(None))
    if parent_id:
        query = query.where(Task.parent_id == parse(ET, parent_id, "parent_id"))
    if due_before:
        query = query.where(Task.due_date < due_before)
    if due_on:
        query = query.where(Task.due_date == due_on)
    if do_date:
        query = query.where(Task.do_date == do_date)
    if overdue:
        query = query.where(Task.due_date < ctx.today(), Task.status.in_(OPEN))
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Task.title.ilike(like), Task.description.ilike(like), Task.notes.ilike(like)))
    all_rows = ctx.db.scalars(
        query.order_by(Task.due_date.asc().nulls_last(), PRIORITY_RANK, Task.id).limit(limit + 1).offset(offset)
    ).all()
    truncated = len(all_rows) > limit
    rows = all_rows[:limit]
    return {"tasks": tasks_out(ctx, rows), "count": len(rows), "truncated": truncated}


def _check_project(ctx: Ctx, value: str | None) -> int | None:
    if value is None:
        return None
    return get_live(ctx, "project", Project, value, "project_id").id


def _linked_future_entries(ctx: Ctx, task_id: int) -> list[CalendarEntry]:
    return list(
        ctx.db.scalars(
            select(CalendarEntry).where(
                CalendarEntry.user_id == ctx.user_id,
                CalendarEntry.task_id == task_id,
                CalendarEntry.deleted_at.is_(None),
                CalendarEntry.status == "planned",
                CalendarEntry.end_at >= ctx.now(),
            )
        )
    )


def save_tasks(ctx: Ctx, items: list[TaskUpsert]) -> dict:
    results = []
    for i, item in enumerate(items):
        with item_ctx(i):
            d = begin(
                ctx, ET, Task, id=item.id, version=item.version, client_ref=item.client_ref,
                defaults={"status": "todo", "priority": "medium"},
            )
            t: Task = d.obj
            vals = only_set(
                item, "title", "description", "status", "priority", "due_date", "do_date",
                "estimated_minutes", "category", "notes",
            )
            for k in ("title", "status", "priority"):
                if k in vals and vals[k] is None:
                    raise validation(f"{k} cannot be null", k)
            if "title" in vals:
                vals["title"] = vals["title"].strip()
                if not vals["title"]:
                    raise validation("title cannot be empty", "title")
            if d.created and not vals.get("title"):
                raise validation("title is required to create a task", "title")
            prev_status = None if d.created else t.status
            if "project_id" in item.model_fields_set:
                vals["project_id"] = _check_project(ctx, item.project_id)
            if "parent_id" in item.model_fields_set:
                if item.parent_id is None:
                    vals["parent_id"] = None
                else:
                    parent = get_live(ctx, ET, Task, item.parent_id, "parent_id")
                    if parent.parent_id is not None:
                        raise validation("Subtasks can only be one level deep", "parent_id")
                    if not d.created and parent.id == t.id:
                        raise validation("A task cannot be its own parent", "parent_id")
                    vals["parent_id"] = parent.id
            apply_fields(t, vals)

            # state machine: completed_at follows status
            if t.status == "done" and prev_status != "done":
                t.completed_at = ctx.now()
            elif t.status != "done" and t.completed_at is not None:
                t.completed_at = None

            if t.due_date and t.do_date and t.do_date > t.due_date:
                ctx.warn("DO_DATE_AFTER_DUE", f"'{t.title}': do_date {t.do_date} is after due_date {t.due_date}")
            if t.do_date and t.do_date < ctx.today() and t.status in OPEN:
                ctx.warn("DO_DATE_IN_PAST", f"'{t.title}': do_date {t.do_date} is in the past")

            action = finish(ctx, d, ET, t.title)
            if t.status in ("done", "cancelled") and prev_status not in ("done", "cancelled", None):
                future = _linked_future_entries(ctx, t.id)
                if future:
                    ctx.warn(
                        "TASK_HAS_FUTURE_BLOCKS",
                        f"{fmt(ET, t.id)} is {t.status} but still has planned blocks: "
                        + ", ".join(fmt("calendar_entry", e.id) for e in future),
                        entries=[fmt("calendar_entry", e.id) for e in future],
                    )
            results.append({"action": action, "task": tasks_out(ctx, [t])[0]})
    return {"results": results}


def delete_task(ctx: Ctx, t: Task) -> dict:
    """Soft delete. Subtasks go with it; linked calendar entries are unlinked (all recorded for undo)."""
    subs = ctx.db.scalars(
        select(Task).where(Task.user_id == ctx.user_id, Task.parent_id == t.id, Task.deleted_at.is_(None))
    ).all()
    for s in subs:
        soft_delete(ctx, ET, s, s.title)
    unlinked = 0
    linked = ctx.db.scalars(
        select(CalendarEntry).where(
            CalendarEntry.user_id == ctx.user_id, CalendarEntry.task_id == t.id, CalendarEntry.deleted_at.is_(None)
        )
    ).all()
    for e in linked:
        d = Draft(e, False, audit.snapshot(e))
        e.task_id = None
        finish(ctx, d, "calendar_entry", e.title)
        unlinked += 1
    soft_delete(ctx, ET, t, t.title)
    return {"deleted_subtasks": len(subs), "unlinked_entries": unlinked}
