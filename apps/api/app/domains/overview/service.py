"""get_context: the one call that bootstraps a conversation, plus the generic delete dispatcher."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.core.crud import compact, get_live
from app.core.ctx import Ctx
from app.core.errors import validation
from app.core.ids import PREFIX, fmt
from app.core.timeutil import day_bounds, iso, weekday_name
from app.domains.audit.models import OperationLog
from app.domains.calendar import service as cal
from app.domains.calendar.models import CalendarEntry
from app.domains.identity import service as identity
from app.domains.planning import service as planning
from app.domains.projects import service as projects
from app.domains.projects.models import Project
from app.domains.routines import service as routines
from app.domains.routines.models import Routine
from app.domains.study import service as study
from app.domains.study.models import StudySession, StudyTopic
from app.domains.tasks import service as tasks
from app.domains.tasks.models import Task


def get_context(ctx: Ctx) -> dict:
    now = ctx.now().astimezone(ctx.tz)
    today = ctx.today()
    tz = ctx.tz

    # --- today
    day = planning.get_schedule(ctx, today, today)["days"][0]
    # --- tasks
    open_q = select(Task).where(
        Task.user_id == ctx.user_id, Task.deleted_at.is_(None), Task.status.in_(tasks.OPEN)
    )
    overdue = ctx.db.scalars(
        open_q.where(Task.due_date < today).order_by(Task.due_date, tasks.PRIORITY_RANK).limit(10)
    ).all()
    today_tasks = ctx.db.scalars(
        open_q.where((Task.do_date == today) | (Task.due_date == today)).order_by(tasks.PRIORITY_RANK).limit(20)
    ).all()
    inbox_count = ctx.db.scalar(
        select(func.count(Task.id)).where(
            Task.user_id == ctx.user_id, Task.deleted_at.is_(None), Task.status == "inbox"
        )
    )
    open_count = ctx.db.scalar(
        select(func.count(Task.id)).where(
            Task.user_id == ctx.user_id, Task.deleted_at.is_(None), Task.status.in_(tasks.OPEN)
        )
    )
    next3 = ctx.db.scalar(
        select(func.count(Task.id)).where(
            Task.user_id == ctx.user_id, Task.deleted_at.is_(None), Task.status.in_(tasks.OPEN),
            Task.due_date >= today, Task.due_date <= today + timedelta(days=3),
        )
    )
    # --- projects
    projs = ctx.db.scalars(
        select(Project).where(Project.user_id == ctx.user_id, Project.deleted_at.is_(None), Project.status == "active")
        .order_by(Project.name)
    ).all()
    pstats = projects._stats(ctx, [p.id for p in projs])
    # --- routines + study
    nodes, roots = study.load_tree(ctx)
    available = study.available_topics(ctx, nodes, roots, limit=8)
    # --- upcoming fixed entries (next 7 days)
    ws, we = day_bounds(today, tz)[0], day_bounds(today + timedelta(days=7), tz)[1]
    maps_entries = [
        o for o in cal.occurrences(ctx, ws, we) if o.entry.mobility == "fixed" and not o.entry.all_day
        and o.start >= ctx.now()
    ][:12]
    cmaps = cal.LinkMaps(ctx, [o.entry for o in maps_entries])
    # --- what the user changed by hand recently (so I notice their edits)
    since = ctx.now() - timedelta(hours=24)
    manual = ctx.db.scalars(
        select(OperationLog)
        .where(OperationLog.user_id == ctx.user_id, OperationLog.actor == "manual", OperationLog.ts >= since,
               OperationLog.result == "ok", OperationLog.action != "reject")
        .order_by(OperationLog.ts.desc()).limit(8)
    ).all()

    return {
        "now": iso(now, tz),
        "today": today.isoformat(),
        "weekday": weekday_name(today),
        "timezone": ctx.prefs_row().timezone,
        "preferences": identity.prefs_out(ctx),
        "today_schedule": {
            "plan": day.get("plan"),
            "all_day": day.get("all_day"),
            "entries": day["entries"],
            "free_windows": day.get("free_windows", []),
            "stats": day["stats"],
        },
        "tasks": {
            "open": open_count,
            "inbox": inbox_count,
            "due_next_3_days": next3,
            "overdue": tasks.tasks_out(ctx, list(overdue), detail=False),
            "for_today": tasks.tasks_out(ctx, list(today_tasks), detail=False),
        },
        "projects": [project_row(p, pstats[p.id]) for p in projs],
        "routines": routines.get_routines(ctx, slim=True),
        "study": {"overview": study.study_overview(nodes), "available_next": available},
        "upcoming_fixed": [cal.entry_out(ctx, o, cmaps) for o in maps_entries],
        "recent_manual_changes": [
            {"ts": iso(m.ts, tz), "action": m.action, "entity": fmt(m.entity_type, m.entity_id) if m.entity_type else None,
             "summary": m.summary} for m in manual
        ],
    }


def project_row(p: Project, stats: dict) -> dict:
    return compact(
        {"id": fmt("project", p.id), "name": p.name, "area": p.area, "open_tasks": stats.get("open_tasks"),
         "overdue_tasks": stats.get("overdue_tasks"), "last_activity": stats.get("last_activity")}
    )


# --------------------------------------------------------------------------- generic delete

DELETABLE = ("task", "calendar_entry", "project", "study_topic", "study_session", "routine", "workout_session")


def delete_entity(ctx: Ctx, entity_type: str, ident: str, *, scope: str = "all",
                  occurrence_start: datetime | None = None, confirm_fixed: bool = False,
                  reason: str | None = None) -> dict:
    from app.core.crud import soft_delete

    if entity_type not in DELETABLE:
        raise validation(f"entity_type must be one of {list(DELETABLE)}", "entity_type")
    from app.domains.audit.service import MODELS

    if entity_type == "calendar_entry":
        res = cal.delete_entry(
            ctx, ident, scope=scope, occurrence_start=occurrence_start, confirm_fixed=confirm_fixed, reason=reason
        )
        return {"deleted": ident, **res}
    obj = get_live(ctx, entity_type, MODELS[entity_type], ident)
    if entity_type == "task":
        res = tasks.delete_task(ctx, obj)
    elif entity_type == "project":
        res = projects.delete_project(ctx, obj)
    elif entity_type == "study_topic":
        res = study.delete_topic(ctx, obj)
    elif entity_type == "routine":
        res = routines.delete_routine(ctx, obj)
    else:
        soft_delete(ctx, entity_type, obj, f"sessão {obj.session_date}")
        res = {}
    return {"deleted": ident, **res}
