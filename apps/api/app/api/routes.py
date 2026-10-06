"""REST API consumed by the web app. Thin: every endpoint calls the same services the MCP tools call."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.deps import current_user, extract_token, first_result, read, respond, write
from app.core import db as dbmod, ratelimit
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import create_token
from app.domains.audit import service as audit
from app.domains.calendar import service as cal
from app.domains.identity import service as identity
from app.domains.identity.models import User
from app.domains.identity.schemas import ChangePasswordIn, LoginIn, PreferencesPatch
from app.domains.overview import service as overview
from app.domains.planning import service as planning
from app.domains.projects import service as projects
from app.domains.routines import service as routines
from app.domains.study import service as study
from app.domains.tasks import service as tasks

router = APIRouter()
TEN_YEARS = 60 * 60 * 24 * 365 * 10

# ---------------------------------------------------------------- auth
def _set_cookie(resp: Response, token: str) -> None:
    s = get_settings()
    resp.set_cookie(
        s.session_cookie_name, token, max_age=TEN_YEARS, httponly=True, samesite="lax",
        secure=s.is_production, path="/",
    )


@router.post("/auth/login")
def login(body: LoginIn, request: Request):
    ip = request.client.host if request.client else "?"
    if ratelimit.blocked(ip):
        return JSONResponse({"ok": False, "error": {"code": "RATE_LIMITED", "message": "Muitas tentativas. Aguarde alguns minutos."}}, 429)
    with dbmod.SessionLocal() as db:
        user = identity.authenticate(db, body.email, body.password)
        if user is None:
            ratelimit.record_failure(ip)
            return JSONResponse({"ok": False, "error": {"code": "UNAUTHORIZED", "message": "E-mail ou senha inválidos."}}, 401)
        token = create_token(user.id, user.token_version)
        out = {"ok": True, "data": {"token": token, "user": {"id": user.id, "email": user.email, "name": user.name}}}
    resp = JSONResponse(out)
    _set_cookie(resp, token)
    return resp


@router.post("/auth/logout")
def logout():
    resp = JSONResponse({"ok": True, "data": {}})
    resp.delete_cookie(get_settings().session_cookie_name, path="/")
    return resp


@router.get("/auth/me")
def me(request: Request, user: User = Depends(current_user)):
    base = (get_settings().public_url or str(request.base_url)).rstrip("/")
    return {"ok": True, "data": {"id": user.id, "email": user.email, "name": user.name, "mcp_url": f"{base}/mcp"}}


@router.post("/auth/change-password")
def change_password(body: ChangePasswordIn, user: User = Depends(current_user)):
    with dbmod.SessionLocal() as db:
        u = db.get(User, user.id)
        try:
            identity.change_password(db, u, body.current_password, body.new_password)
        except AppError as e:
            return respond((e.http_status, {"ok": False, "error": e.to_dict()}))
        token = create_token(u.id, u.token_version)
    resp = JSONResponse({"ok": True, "data": {"token": token}})
    _set_cookie(resp, token)
    return resp


@router.post("/auth/revoke-all")
def revoke_all(user: User = Depends(current_user)):
    """Invalidates every token ever issued (other devices, MCP connectors). This session gets a fresh one."""
    with dbmod.SessionLocal() as db:
        u = db.get(User, user.id)
        identity.revoke_all(db, u)
        token = create_token(u.id, u.token_version)
    resp = JSONResponse({"ok": True, "data": {"token": token}})
    _set_cookie(resp, token)
    return resp


@router.get("/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------- context / schedule
@router.get("/context")
def context(user: User = Depends(current_user)):
    return read(user, "get_context", overview.get_context)


@router.get("/schedule")
def schedule(start: date, end: date, free: bool = True, user: User = Depends(current_user)):
    return read(user, "get_schedule", lambda ctx: planning.get_schedule(ctx, start, end, include_free=free))


@router.put("/plans")
def put_plans(plans: list[planning.DayPlanIn], dry_run: bool = False, user: User = Depends(current_user)):
    return write(user, "set_day_plan", lambda ctx: planning.set_day_plan(ctx, plans), dry_run)


# ---------------------------------------------------------------- calendar
@router.post("/calendar")
def create_entry(item: cal.EntryUpsert, user: User = Depends(current_user)):
    item.id = None
    return write(user, "save_calendar_entries", lambda ctx: _one(cal.save_entries(ctx, [item])))


@router.patch("/calendar/{entry_id}")
def patch_entry(entry_id: str, item: cal.EntryUpsert, user: User = Depends(current_user)):
    item.id = entry_id
    return write(user, "save_calendar_entries", lambda ctx: _one(cal.save_entries(ctx, [item])))


@router.delete("/calendar/{entry_id}")
def delete_entry(entry_id: str, scope: str = "all", occurrence_start: datetime | None = None,
                 user: User = Depends(current_user)):
    return write(
        user, "delete_entity",
        lambda ctx: overview.delete_entity(ctx, "calendar_entry", entry_id, scope=scope, occurrence_start=occurrence_start),
    )


def _one(data: dict) -> dict:
    return first_result(data)


# ---------------------------------------------------------------- tasks
@router.get("/tasks")
def list_tasks(
    status: list[str] | None = Query(None), project_id: str | None = None, due_before: date | None = None,
    due_on: date | None = None, do_date: date | None = None, overdue: bool | None = None,
    no_project: bool | None = None, q: str | None = None, include_done_since: date | None = None,
    parent_id: str | None = None, ids: list[str] | None = Query(None), limit: int = 200, offset: int = 0,
    user: User = Depends(current_user),
):
    return read(
        user, "list_tasks",
        lambda ctx: tasks.list_tasks(
            ctx, ids=ids, status=status, project_id=project_id, parent_id=parent_id, due_before=due_before,
            due_on=due_on, do_date=do_date, overdue=overdue, no_project=no_project, q=q,
            include_done_since=include_done_since, limit=min(limit, 500), offset=offset,
        ),
    )


@router.post("/tasks")
def create_task(item: tasks.TaskUpsert, user: User = Depends(current_user)):
    item.id = None
    return write(user, "save_tasks", lambda ctx: _one(tasks.save_tasks(ctx, [item])))


@router.patch("/tasks/{task_id}")
def patch_task(task_id: str, item: tasks.TaskUpsert, user: User = Depends(current_user)):
    item.id = task_id
    return write(user, "save_tasks", lambda ctx: _one(tasks.save_tasks(ctx, [item])))


# ---------------------------------------------------------------- projects
@router.get("/projects")
def list_projects(status: str | None = None, user: User = Depends(current_user)):
    return read(user, "get_projects", lambda ctx: projects.get_projects(ctx, None, status))


@router.get("/projects/{project_id}")
def get_project(project_id: str, user: User = Depends(current_user)):
    return read(user, "get_projects", lambda ctx: projects.get_projects(ctx, project_id))


@router.post("/projects")
def create_project(item: projects.ProjectUpsert, user: User = Depends(current_user)):
    item.id = None
    return write(user, "save_projects", lambda ctx: _one(projects.save_projects(ctx, [item])))


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, item: projects.ProjectUpsert, user: User = Depends(current_user)):
    item.id = project_id
    return write(user, "save_projects", lambda ctx: _one(projects.save_projects(ctx, [item])))


# ---------------------------------------------------------------- study
@router.get("/study")
def get_study(topic_id: str | None = None, depth: int = 3, only_available: bool = False, only_open: bool = False,
              user: User = Depends(current_user)):
    return read(
        user, "get_study",
        lambda ctx: study.get_study(ctx, topic_id, depth=depth, only_available=only_available, only_open=only_open,
                                    limit=200),
    )


@router.post("/study/topics")
def create_topic(item: study.StudyTopicUpsert, user: User = Depends(current_user)):
    item.id = None
    return write(user, "save_study_topics", lambda ctx: study.save_topics(ctx, [item]))


@router.patch("/study/topics/{topic_id}")
def patch_topic(topic_id: str, item: study.StudyTopicUpsert, user: User = Depends(current_user)):
    item.id = topic_id
    return write(user, "save_study_topics", lambda ctx: study.save_topics(ctx, [item]))


class _LogIn(BaseModel):
    topic_id: str
    minutes: int
    date: datetime | None = None
    notes: str | None = None
    progress: int | None = None
    status: str | None = None
    entry_id: str | None = None
    mark_entry_done: bool = False


@router.post("/study/log")
def log_study(body: _LogIn, user: User = Depends(current_user)):
    return write(
        user, "log_study",
        lambda ctx: study.log_study(
            ctx, body.topic_id, body.minutes, body.date.date() if body.date else None, body.notes, body.progress, body.status, body.entry_id,
            body.mark_entry_done,
        ),
    )


# ---------------------------------------------------------------- routines
@router.get("/routines")
def list_routines(include_inactive: bool = False, sessions: int = 0, user: User = Depends(current_user)):
    return read(
        user, "get_routines",
        lambda ctx: {"routines": routines.get_routines(ctx, include_inactive, sessions=min(sessions, 30))},
    )


@router.post("/workouts")
def log_workout(item: routines.WorkoutLogIn, user: User = Depends(current_user)):
    return write(user, "log_workout", lambda ctx: routines.log_workout(ctx, item))


@router.patch("/workouts/{session_id}")
def patch_workout(session_id: str, item: routines.WorkoutLogIn, user: User = Depends(current_user)):
    item.id = session_id
    return write(user, "log_workout", lambda ctx: routines.log_workout(ctx, item))


@router.get("/workouts/{session_id}")
def get_workout(session_id: str, user: User = Depends(current_user)):
    return read(user, "get_workout", lambda ctx: routines.get_workout(ctx, session_id))


@router.post("/routines")
def create_routine(item: routines.RoutineUpsert, user: User = Depends(current_user)):
    item.id = None
    return write(user, "save_routines", lambda ctx: _one(routines.save_routines(ctx, [item])))


@router.patch("/routines/{routine_id}")
def patch_routine(routine_id: str, item: routines.RoutineUpsert, user: User = Depends(current_user)):
    item.id = routine_id
    return write(user, "save_routines", lambda ctx: _one(routines.save_routines(ctx, [item])))


# ---------------------------------------------------------------- generic delete
@router.delete("/{entity_type}/{ident}")
def delete_any(entity_type: str, ident: str, user: User = Depends(current_user)):
    mapping = {
        "tasks": "task", "projects": "project", "routines": "routine", "study-topics": "study_topic",
        "study-sessions": "study_session", "workout-sessions": "workout_session",
    }
    et = mapping.get(entity_type)
    if et is None:
        return JSONResponse({"ok": False, "error": {"code": "NOT_FOUND", "message": "Unknown resource"}}, 404)
    return write(user, "delete_entity", lambda ctx: overview.delete_entity(ctx, et, ident))


# ---------------------------------------------------------------- preferences / audit
@router.get("/preferences")
def get_preferences(user: User = Depends(current_user)):
    return read(user, "get_preferences", identity.prefs_out)


@router.patch("/preferences")
def patch_preferences(patch: PreferencesPatch, user: User = Depends(current_user)):
    return write(user, "save_preferences", lambda ctx: identity.save_preferences(ctx, patch))


@router.get("/operations")
def operations(since_hours: int = 72, actor: str | None = None, limit: int = 40, user: User = Depends(current_user)):
    return read(
        user, "get_operation_log",
        lambda ctx: audit.list_batches(ctx, since_hours=since_hours, actor=actor, limit=limit),
    )


@router.post("/operations/{batch_id}/undo")
def undo(batch_id: str, user: User = Depends(current_user)):
    return write(user, "undo_operation", lambda ctx: audit.undo_batch(ctx, batch_id))
