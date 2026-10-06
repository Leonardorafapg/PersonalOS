from __future__ import annotations

import uuid
from datetime import date as date_t
from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.crud import Draft, apply_fields, begin, compact, finish, get_live, item_ctx, only_set, soft_delete
from app.core.ctx import Ctx
from app.core.errors import validation
from app.core.ids import fmt
from app.core.timeutil import day_bounds, minutes_between, to_utc, week_start
from app.domains.audit import service as audit
from app.domains.calendar.models import CalendarEntry
from app.domains.identity.schemas import HHMM
from app.domains.routines.models import Routine, WorkoutSession

ET = "routine"
EW = "workout_session"
MAX_WORKOUTS = 12
MAX_EXERCISES = 60


def _key() -> str:
    return uuid.uuid4().hex[:6]


# --------------------------------------------------------------------------- schemas

class Exercise(BaseModel):
    """One exercise of a workout template."""

    key: str | None = Field(None, description="Stable id; keep it when editing so history lines up. Auto-generated if omitted")
    name: str
    sets: int | None = Field(None, ge=1, le=50)
    reps: str | None = Field(None, description="Free text: '10', '8-12', '30s', 'até a falha'")
    load: str | None = Field(None, description="Free text: '40kg', 'peso do corpo', 'faixa roxa'")
    rest_seconds: int | None = Field(None, ge=0, le=1800)
    notes: str | None = None


class Workout(BaseModel):
    """A named session inside a routine, e.g. 'Treino A · Peito e tríceps' or 'Aula · drills'."""

    key: str | None = None
    name: str
    exercises: list[Exercise] = Field(default_factory=list)


class RoutineUpsert(BaseModel):
    """A cadence template (e.g. Jiu-Jitsu 3x/week) with an optional exercise plan (`workouts`).
    Concrete sessions are calendar entries linked via routine_id."""

    id: str | None = None
    version: int | None = None
    client_ref: str | None = None
    kind: Literal["training"] | None = None
    name: str | None = None
    description: str | None = None
    target_per_week: int | None = Field(None, ge=0, le=21)
    duration_minutes: int | None = Field(None, ge=5, le=600)
    preferred_days: list[int] | None = Field(None, description="0=Mon .. 6=Sun")
    preferred_start: str | None = Field(None, description="HH:MM preferred start time")
    preferred_end: str | None = Field(None, description="HH:MM latest preferred end")
    notes: str | None = None
    active: bool | None = None
    workouts: list[Workout] | None = Field(
        None, description="The exercise plan. Replaces the whole plan when sent; keep existing `key`s to preserve history"
    )


class ExerciseLog(BaseModel):
    """State of one exercise in a performed workout. Match by `key` (preferred) or `name`; unknown names are added."""

    key: str | None = None
    name: str | None = None
    done: bool | None = Field(None, description="true = done, false = not done, null = pending")
    actual: str | None = Field(None, description="What was really done, e.g. '3x10 @ 42kg'")
    note: str | None = None
    sets: int | None = None
    reps: str | None = None
    load: str | None = None


class WorkoutLogIn(BaseModel):
    """Start / update / finish a workout session. Re-sending with the same entry_id (or same routine+date+workout
    while unfinished) resumes the existing session instead of creating another."""

    id: str | None = Field(None, description="Existing session id (e.g. 'ws3') to update; needs version")
    version: int | None = None
    routine_id: str | None = Field(None, description="Required when creating, unless entry_id points to a routine entry")
    workout_key: str | None = Field(None, description="Which workout of the routine; optional when it has only one")
    date: date_t | None = Field(None, description="Defaults to today (or the entry's day)")
    entry_id: str | None = Field(None, description="The calendar entry this session fulfils")
    occurrence_start: datetime | None = Field(None, description="Needed when entry_id is a recurring series")
    exercises: list[ExerciseLog] | None = None
    notes: str | None = None
    effort: int | None = Field(None, ge=1, le=10, description="Perceived effort 1-10")
    duration_minutes: int | None = Field(None, ge=1, le=600)
    finished: bool | None = Field(
        None,
        description="true = finish: pending exercises become 'not done' and the linked entry is marked done. "
        "false = reopen",
    )


# --------------------------------------------------------------------------- templates

def normalize_workouts(items: list[Workout]) -> list[dict]:
    if len(items) > MAX_WORKOUTS:
        raise validation(f"At most {MAX_WORKOUTS} workouts per routine", "workouts")
    out, wkeys = [], set()
    for w in items:
        name = w.name.strip()
        if not name:
            raise validation("Every workout needs a name", "workouts")
        wk = (w.key or "").strip() or _key()
        if wk in wkeys:
            raise validation(f"Duplicate workout key '{wk}'", "workouts")
        wkeys.add(wk)
        if len(w.exercises) > MAX_EXERCISES:
            raise validation(f"At most {MAX_EXERCISES} exercises per workout", "workouts")
        exs, ekeys = [], set()
        for e in w.exercises:
            en = e.name.strip()
            if not en:
                raise validation(f"Workout '{name}' has an exercise without a name", "workouts")
            ek = (e.key or "").strip() or _key()
            if ek in ekeys:
                raise validation(f"Duplicate exercise key '{ek}' in '{name}'", "workouts")
            ekeys.add(ek)
            exs.append(compact({"key": ek, "name": en, "sets": e.sets, "reps": (e.reps or "").strip() or None,
                                "load": (e.load or "").strip() or None, "rest_seconds": e.rest_seconds,
                                "notes": (e.notes or "").strip() or None}))
        out.append({"key": wk, "name": name, "exercises": exs})
    return out


def workouts_out(r: Routine, slim: bool) -> list[dict]:
    ws = r.workouts or []
    if slim:
        return [{"key": w["key"], "name": w["name"], "exercises": len(w.get("exercises", []))} for w in ws]
    return ws


# --------------------------------------------------------------------------- reading

def week_progress(ctx: Ctx, routine_ids: list[int]) -> dict[int, dict]:
    today = ctx.today()
    ws = week_start(today)
    start, _ = day_bounds(ws, ctx.tz)
    _, end = day_bounds(ws + timedelta(days=6), ctx.tz)
    out = {rid: {"done_this_week": 0, "planned_this_week": 0} for rid in routine_ids}
    if not routine_ids:
        return out
    rows = ctx.db.scalars(
        select(CalendarEntry).where(
            CalendarEntry.user_id == ctx.user_id, CalendarEntry.deleted_at.is_(None),
            CalendarEntry.routine_id.in_(routine_ids), CalendarEntry.start_at >= start, CalendarEntry.start_at < end,
            CalendarEntry.rrule.is_(None),
        )
    ).all()
    for e in rows:
        if e.status == "done":
            out[e.routine_id]["done_this_week"] += 1
        elif e.status == "planned":
            out[e.routine_id]["planned_this_week"] += 1
    return out


def routine_out(ctx: Ctx, r: Routine, prog: dict | None = None, *, slim: bool = False) -> dict:
    d = {
        "id": fmt(ET, r.id), "kind": r.kind, "name": r.name, "description": r.description,
        "target_per_week": r.target_per_week, "duration_minutes": r.duration_minutes,
        "preferred_days": r.preferred_days, "preferred_start": r.preferred_start, "preferred_end": r.preferred_end,
        "notes": r.notes, "active": r.active, "version": r.version, "workouts": workouts_out(r, slim),
    }
    if prog:
        d.update(prog)
    out = compact(d)
    out["active"] = r.active
    return out


def summarize(exercises: list[dict]) -> dict:
    done = sum(1 for e in exercises if e.get("done") is True)
    skipped = sum(1 for e in exercises if e.get("done") is False)
    return {"total": len(exercises), "done": done, "not_done": skipped, "pending": len(exercises) - done - skipped}


def session_out(ctx: Ctx, s: WorkoutSession, *, brief: bool = False, routine_name: str | None = None) -> dict:
    d = {
        "id": fmt(EW, s.id),
        "routine_id": fmt(ET, s.routine_id),
        "routine_name": routine_name,
        "date": s.session_date.isoformat(),
        "workout_key": s.workout_key,
        "workout_name": s.workout_name,
        "entry_id": fmt("calendar_entry", s.entry_id),
        "finished": s.finished,
        "summary": summarize(s.exercises or []),
        "effort": s.effort,
        "duration_minutes": s.duration_minutes,
        "notes": s.notes,
        "version": s.version,
        "created_by": s.created_by,
    }
    if not brief:
        d["exercises"] = s.exercises or []
    out = compact(d)
    out["finished"] = s.finished
    return out


def recent_sessions(ctx: Ctx, routine_id: int, limit: int) -> list[WorkoutSession]:
    return list(
        ctx.db.scalars(
            select(WorkoutSession)
            .where(WorkoutSession.user_id == ctx.user_id, WorkoutSession.routine_id == routine_id,
                   WorkoutSession.deleted_at.is_(None))
            .order_by(WorkoutSession.session_date.desc(), WorkoutSession.id.desc())
            .limit(limit)
        )
    )


def get_routines(ctx: Ctx, include_inactive: bool = False, *, routine_id: str | None = None, sessions: int = 0,
                 slim: bool = False) -> list[dict]:
    q = select(Routine).where(Routine.user_id == ctx.user_id, Routine.deleted_at.is_(None))
    if routine_id:
        q = q.where(Routine.id == get_live(ctx, ET, Routine, routine_id, "routine_id").id)
    elif not include_inactive:
        q = q.where(Routine.active.is_(True))
    rows = ctx.db.scalars(q.order_by(Routine.name)).all()
    prog = week_progress(ctx, [r.id for r in rows])
    out = []
    for r in rows:
        d = routine_out(ctx, r, prog[r.id], slim=slim)
        if sessions:
            d["recent_sessions"] = [session_out(ctx, s, brief=True) for s in recent_sessions(ctx, r.id, sessions)]
        out.append(d)
    return out


def get_workout(ctx: Ctx, ident: str) -> dict:
    s = get_live(ctx, EW, WorkoutSession, ident)
    r = ctx.db.get(Routine, s.routine_id)
    return {"session": session_out(ctx, s, routine_name=r.name if r else None)}


# --------------------------------------------------------------------------- writing

def save_routines(ctx: Ctx, items: list[RoutineUpsert]) -> dict:
    results = []
    for i, item in enumerate(items):
        with item_ctx(i):
            d = begin(
                ctx, ET, Routine, id=item.id, version=item.version, client_ref=item.client_ref,
                defaults={"kind": "training", "target_per_week": 1, "duration_minutes": 60, "active": True,
                          "preferred_days": [], "workouts": []},
            )
            vals = only_set(
                item, "kind", "name", "description", "target_per_week", "duration_minutes", "preferred_days",
                "preferred_start", "preferred_end", "notes", "active",
            )
            for k in ("kind", "name", "target_per_week", "duration_minutes", "preferred_days", "active"):
                if k in vals and vals[k] is None:
                    raise validation(f"{k} cannot be null", k)
            if "name" in vals:
                vals["name"] = vals["name"].strip()
                if not vals["name"]:
                    raise validation("name cannot be empty", "name")
            if d.created and not vals.get("name"):
                raise validation("name is required to create a routine", "name")
            if "preferred_days" in vals:
                if any(x < 0 or x > 6 for x in vals["preferred_days"]):
                    raise validation("preferred_days must be 0 (Mon) .. 6 (Sun)", "preferred_days")
                vals["preferred_days"] = sorted(set(vals["preferred_days"]))
            for k in ("preferred_start", "preferred_end"):
                if vals.get(k) is not None and not HHMM.match(vals[k]):
                    raise validation(f"{k} must be HH:MM", k)
            if "workouts" in item.model_fields_set:
                if item.workouts is None:
                    raise validation("workouts cannot be null (send [] to clear)", "workouts")
                vals["workouts"] = normalize_workouts(item.workouts)
            apply_fields(d.obj, vals)
            action = finish(ctx, d, ET, d.obj.name)
            results.append({"action": action, "routine": routine_out(ctx, d.obj)})
    return {"results": results}


def delete_routine(ctx: Ctx, r: Routine) -> dict:
    linked = ctx.db.scalars(
        select(CalendarEntry).where(
            CalendarEntry.user_id == ctx.user_id, CalendarEntry.routine_id == r.id, CalendarEntry.deleted_at.is_(None)
        )
    ).all()
    for e in linked:
        d = Draft(e, False, audit.snapshot(e))
        e.routine_id = None
        finish(ctx, d, "calendar_entry", e.title)
    n = 0
    for s in recent_sessions(ctx, r.id, 10_000):
        soft_delete(ctx, EW, s, f"treino {s.session_date}")
        n += 1
    soft_delete(ctx, ET, r, r.name)
    return {"unlinked_entries": len(linked), "deleted_sessions": n}


# ---- workout sessions

def _resolve_entry(ctx: Ctx, entry_id: str, occurrence_start: datetime | None) -> CalendarEntry:
    """Find the concrete calendar row for an entry; materialize one occurrence of a series if needed."""
    from app.domains.calendar import service as cal

    e = get_live(ctx, "calendar_entry", CalendarEntry, entry_id, "entry_id")
    if not e.rrule:
        return e
    if occurrence_start is None:
        raise validation("entry_id is a recurring series: send occurrence_start too", "occurrence_start")
    occ = to_utc(occurrence_start, ctx.tz)
    row = ctx.db.scalars(
        select(CalendarEntry).where(
            CalendarEntry.user_id == ctx.user_id, CalendarEntry.series_id == e.id,
            CalendarEntry.original_start == occ, CalendarEntry.deleted_at.is_(None),
        )
    ).first()
    if row:
        return row
    res = cal.save_entries(ctx, [cal.EntryUpsert(id=fmt("calendar_entry", e.id), scope="this", occurrence_start=occurrence_start)])
    return get_live(ctx, "calendar_entry", CalendarEntry, res["results"][0]["entry"]["id"])


def _snapshot(workout: dict | None) -> list[dict]:
    if not workout:
        return []
    out = []
    for ex in workout.get("exercises", []):
        out.append({**ex, "done": None})
    return out


def _find_ex(exs: list[dict], log: ExerciseLog) -> dict | None:
    if log.key:
        for e in exs:
            if e.get("key") == log.key:
                return e
    if log.name:
        for e in exs:
            if e["name"].strip().lower() == log.name.strip().lower():
                return e
    return None


def log_workout(ctx: Ctx, item: WorkoutLogIn) -> dict:
    from app.domains.calendar import service as cal

    entry = _resolve_entry(ctx, item.entry_id, item.occurrence_start) if item.entry_id else None
    routine_ref = item.routine_id or (fmt(ET, entry.routine_id) if entry and entry.routine_id else None)
    sent = item.model_fields_set

    if item.id:
        d = begin(ctx, EW, WorkoutSession, id=item.id, version=item.version)
        s: WorkoutSession = d.obj
        routine = ctx.db.get(Routine, s.routine_id)
    else:
        if not routine_ref:
            raise validation("routine_id is required (or an entry_id linked to a routine)", "routine_id")
        routine = get_live(ctx, ET, Routine, routine_ref, "routine_id")
        if entry and entry.routine_id and entry.routine_id != routine.id:
            raise validation("entry_id belongs to a different routine", "entry_id")
        day = item.date or (entry.start_at.astimezone(ctx.tz).date() if entry else ctx.today())
        existing = None
        if entry:
            existing = ctx.db.scalars(
                select(WorkoutSession).where(
                    WorkoutSession.user_id == ctx.user_id, WorkoutSession.entry_id == entry.id,
                    WorkoutSession.deleted_at.is_(None),
                )
            ).first()
        if existing is None:
            q = select(WorkoutSession).where(
                WorkoutSession.user_id == ctx.user_id, WorkoutSession.routine_id == routine.id,
                WorkoutSession.session_date == day, WorkoutSession.finished.is_(False),
                WorkoutSession.deleted_at.is_(None),
            )
            if item.workout_key:
                q = q.where(WorkoutSession.workout_key == item.workout_key)
            existing = ctx.db.scalars(q.order_by(WorkoutSession.id.desc())).first() if not entry else None
        if existing is not None:
            d = Draft(existing, False, audit.snapshot(existing))
            s = existing
        else:
            workouts = routine.workouts or []
            chosen = None
            if item.workout_key:
                chosen = next((w for w in workouts if w["key"] == item.workout_key), None)
                if chosen is None:
                    raise validation(
                        f"Unknown workout_key '{item.workout_key}'. Available: "
                        + ", ".join(f"{w['key']} ({w['name']})" for w in workouts), "workout_key")
            elif len(workouts) == 1:
                chosen = workouts[0]
            elif len(workouts) > 1:
                raise validation(
                    "This routine has several workouts; send workout_key. Available: "
                    + ", ".join(f"{w['key']} ({w['name']})" for w in workouts), "workout_key")
            s = WorkoutSession(
                user_id=ctx.user_id, created_by=ctx.actor, updated_by=ctx.actor, routine_id=routine.id,
                session_date=day, workout_key=chosen["key"] if chosen else None,
                workout_name=chosen["name"] if chosen else routine.name, entry_id=entry.id if entry else None,
                exercises=_snapshot(chosen), finished=False,
            )
            d = Draft(s, True, None)

    if entry is not None and s.entry_id is None:
        s.entry_id = entry.id

    # exercise states
    if item.exercises:
        exs = [dict(e) for e in (s.exercises or [])]
        for log in item.exercises:
            ex = _find_ex(exs, log)
            if ex is None:
                if not (log.name or "").strip():
                    raise validation("Unknown exercise key; send a name to add a new exercise", "exercises")
                ex = {"key": _key(), "name": log.name.strip(), "extra": True, "done": None}
                exs.append(ex)
            fs = log.model_fields_set
            if "done" in fs:
                ex["done"] = log.done
            for f in ("actual", "note", "sets", "reps", "load"):
                if f in fs:
                    if getattr(log, f) in (None, ""):
                        ex.pop(f, None)
                    else:
                        ex[f] = getattr(log, f)
        if len(exs) > MAX_EXERCISES:
            raise validation(f"At most {MAX_EXERCISES} exercises per session", "exercises")
        s.exercises = exs
    for f in ("notes", "effort", "duration_minutes"):
        if f in sent:
            setattr(s, f, getattr(item, f))

    marking_done = False
    if item.finished is True and not s.finished:
        s.exercises = [{**e, "done": False} if e.get("done") is None else e for e in (s.exercises or [])]
        s.finished = True
        marking_done = True
        src = entry or (ctx.db.get(CalendarEntry, s.entry_id) if s.entry_id else None)
        if s.duration_minutes is None and src is not None:
            s.duration_minutes = max(1, minutes_between(src.start_at, src.end_at))
    elif item.finished is False:
        s.finished = False

    action = finish(ctx, d, EW, f"{s.workout_name} · {s.session_date}")

    linked = ctx.db.get(CalendarEntry, s.entry_id) if s.entry_id else None
    if marking_done and linked is not None and linked.deleted_at is None and linked.status != "done":
        cal.save_entries(ctx, [cal.EntryUpsert(id=fmt("calendar_entry", linked.id), version=linked.version, status="done")])
        ctx.db.refresh(linked)

    return {"action": action, "session": session_out(ctx, s, routine_name=routine.name if routine else None),
            "entry_status": linked.status if linked is not None else None}
