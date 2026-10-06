"""Day views (schedule + free windows) and the declarative Daily Plan."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.crud import Draft, compact, finish, get_live, soft_delete
from app.core.ctx import Ctx
from app.core.errors import validation
from app.core.ids import fmt, parse
from app.core.timeutil import day_bounds, iso, minutes_between, parse_hhmm, to_utc, weekday_name
from app.domains.audit import service as audit
from app.domains.calendar import service as cal
from app.domains.calendar.models import CalendarEntry
from app.domains.planning.models import DailyPlan

ET = "daily_plan"
MAX_RANGE_DAYS = 42  # a 6-week month grid


# --------------------------------------------------------------------------- schedule

def plan_out(p: DailyPlan | None) -> dict | None:
    if p is None:
        return None
    return compact(
        {
            "id": fmt(ET, p.id),
            "summary": p.summary,
            "rationale": p.rationale,
            "status": p.status,
            "version": p.version,
            "updated_by": p.updated_by,
        }
    )


def _waking_window(ctx: Ctx, d: date) -> tuple[datetime, datetime]:
    prefs = ctx.prefs
    tz = ctx.tz
    wake = datetime.combine(d, parse_hhmm(prefs.wake_time), tzinfo=tz)
    sleep = datetime.combine(d, parse_hhmm(prefs.sleep_time), tzinfo=tz)
    if sleep <= wake:
        sleep += timedelta(days=1)
    return wake, sleep


def _round_up_5(dt: datetime) -> datetime:
    dt = dt.replace(second=0, microsecond=0) + (timedelta(minutes=1) if dt.second or dt.microsecond else timedelta())
    return dt + timedelta(minutes=(5 - dt.minute % 5) % 5)


def free_windows_for_day(ctx: Ctx, d: date, occs: list[cal.Occ] | None = None) -> list[dict]:
    today = ctx.today()
    if d < today:
        return []
    wake, sleep = _waking_window(ctx, d)
    if d == today:
        now = ctx.now().astimezone(ctx.tz)
        wake = max(wake, _round_up_5(now))
    if wake >= sleep:
        return []
    if occs is None:
        occs = cal.occurrences(ctx, wake, sleep)
    busy = sorted(
        (max(o.start, wake), min(o.end, sleep))
        for o in occs
        if o.active and not o.entry.all_day and o.start < sleep and o.end > wake
    )
    merged: list[list[datetime]] = []
    for s, e in busy:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out, cursor = [], wake
    min_len = ctx.prefs.min_free_window_minutes
    for s, e in merged:
        if (s - cursor) >= timedelta(minutes=min_len):
            out.append((cursor, s))
        cursor = max(cursor, e)
    if (sleep - cursor) >= timedelta(minutes=min_len):
        out.append((cursor, sleep))
    return [{"start": iso(s, ctx.tz), "end": iso(e, ctx.tz), "minutes": minutes_between(s, e)} for s, e in out]


def get_schedule(ctx: Ctx, start: date, end: date, *, include_free: bool = True) -> dict:
    if end < start:
        raise validation("end must be on or after start", "end")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise validation(f"Range too large; max {MAX_RANGE_DAYS} days", "end")
    tz = ctx.tz
    win_s, _ = day_bounds(start, tz)
    _, win_e = day_bounds(end, tz)
    occs = [o for o in cal.occurrences(ctx, win_s, win_e, include_inactive=True) if o.entry.status != "cancelled"]
    plans = {
        p.plan_date: p
        for p in ctx.db.scalars(
            select(DailyPlan).where(
                DailyPlan.user_id == ctx.user_id, DailyPlan.deleted_at.is_(None),
                DailyPlan.plan_date >= start, DailyPlan.plan_date <= end,
            )
        )
    }
    maps = cal.LinkMaps(ctx, [o.entry for o in occs])
    today = ctx.today()
    days = []
    d = start
    while d <= end:
        ds, de = day_bounds(d, tz)
        day_all = [o for o in occs if o.entry.all_day and o.start < de and o.end > ds]
        day_timed = [o for o in occs if not o.entry.all_day and ds <= o.start < de]
        # overlaps among active timed entries
        overlaps: dict[int, list[str]] = {}
        active = [o for o in day_timed if o.active]
        for i, a in enumerate(active):
            for b in active[i + 1:]:
                if a.start < b.end and b.start < a.end:
                    overlaps.setdefault(id(a), []).append(fmt("calendar_entry", b.entry.id))
                    overlaps.setdefault(id(b), []).append(fmt("calendar_entry", a.entry.id))
        planned = sum(minutes_between(o.start, o.end) for o in day_timed if o.entry.status in ("planned", "done"))
        done = sum(minutes_between(o.start, o.end) for o in day_timed if o.entry.status == "done")
        free = free_windows_for_day(ctx, d, [o for o in occs if o.start < de and o.end > ds]) if include_free else None
        day = {
            "date": d.isoformat(),
            "weekday": weekday_name(d),
            "is_today": d == today,
            "plan": plan_out(plans.get(d)),
            "all_day": [entry_view(ctx, o, maps, overlaps) for o in day_all],
            "entries": [entry_view(ctx, o, maps, overlaps) for o in day_timed],
            "stats": {
                "planned_minutes": planned,
                "done_minutes": done,
                "entries": sum(1 for o in day_timed if o.entry.status in ("planned", "done")),
                "entries_done": sum(1 for o in day_timed if o.entry.status == "done"),
                "entries_skipped": sum(1 for o in day_timed if o.entry.status == "skipped"),
                "free_minutes": sum(w["minutes"] for w in free) if free is not None else None,
            },
        }
        if free is not None:
            day["free_windows"] = free
        if day["stats"]["free_minutes"] is None:
            del day["stats"]["free_minutes"]
        days.append(day)
        d += timedelta(days=1)
    return {"range": {"start": start.isoformat(), "end": end.isoformat()}, "tz": ctx.prefs_row().timezone, "days": days}


def entry_view(ctx: Ctx, o: cal.Occ, maps: cal.LinkMaps, overlaps: dict) -> dict:
    return cal.entry_out(ctx, o, maps, overlaps=overlaps.get(id(o)))


# --------------------------------------------------------------------------- declarative plan

class PlanBlock(BaseModel):
    """A flexible block you want in the day. Existing blocks are matched by id, else by title+time/links."""

    id: str | None = Field(None, description="Existing block id to keep/move (optional)")
    title: str
    start: datetime
    end: datetime
    category: Literal["work", "study", "training", "meal", "personal", "rest", "other", "meeting", "appointment"] = "work"
    task_id: str | None = None
    study_topic_id: str | None = None
    routine_id: str | None = None
    project_id: str | None = None
    notes: str | None = None


class DayPlanIn(BaseModel):
    date: date
    summary: str | None = Field(None, description="One-line headline for the day")
    rationale: str | None = Field(
        None, description="Why the day is arranged this way. Future-you reads this to stay coherent."
    )
    blocks: list[PlanBlock] = Field(default_factory=list, description="Desired flexible blocks for the day")
    mode: Literal["replace", "merge"] = Field(
        "replace",
        description="replace: flexible planned blocks not listed (and not yet finished) are removed. "
        "merge: only add/update, never remove.",
    )


def _save_plan_row(ctx: Ctx, plan: DayPlanIn) -> DailyPlan:
    row = ctx.db.scalars(
        select(DailyPlan).where(
            DailyPlan.user_id == ctx.user_id, DailyPlan.plan_date == plan.date, DailyPlan.deleted_at.is_(None)
        )
    ).first()
    if row is None:
        row = DailyPlan(
            user_id=ctx.user_id, plan_date=plan.date, created_by=ctx.actor, updated_by=ctx.actor, status="active"
        )
        d = Draft(row, True, None)
    else:
        d = Draft(row, False, audit.snapshot(row))
    if "summary" in plan.model_fields_set:
        row.summary = plan.summary
    if "rationale" in plan.model_fields_set:
        row.rationale = plan.rationale
    row.status = "active"
    finish(ctx, d, ET, f"Plano {plan.date.isoformat()}")
    return row


def set_day_plan(ctx: Ctx, plans: list[DayPlanIn]) -> dict:
    if not plans:
        raise validation("plans cannot be empty", "plans")
    seen_dates = set()
    touched: list[CalendarEntry] = []
    out = []
    for pi, plan in enumerate(plans):
        if plan.date in seen_dates:
            raise validation(f"Date {plan.date} appears twice", "plans")
        seen_dates.add(plan.date)
        row = _save_plan_row(ctx, plan)
        ds, de = day_bounds(plan.date, ctx.tz)
        existing = list(
            ctx.db.scalars(
                select(CalendarEntry).where(
                    CalendarEntry.user_id == ctx.user_id,
                    CalendarEntry.deleted_at.is_(None),
                    CalendarEntry.rrule.is_(None),
                    CalendarEntry.series_id.is_(None),
                    CalendarEntry.mobility == "flexible",
                    CalendarEntry.status != "cancelled",
                    CalendarEntry.all_day.is_(False),
                    CalendarEntry.start_at >= ds,
                    CalendarEntry.start_at < de,
                )
            )
        )
        by_id = {e.id: e for e in existing}
        unmatched = list(existing)
        created, updated, unchanged = [], [], 0
        used: set[int] = set()
        for bi, blk in enumerate(plan.blocks):
            where = f"plans[{pi}].blocks[{bi}]"
            s_utc, e_utc = to_utc(blk.start, ctx.tz), to_utc(blk.end, ctx.tz)
            if not (ds <= s_utc < de):
                raise validation(f"{where}: start {blk.start.isoformat()} is not on {plan.date}", "blocks")
            links = _link_ids(blk)
            match: CalendarEntry | None = None
            if blk.id:
                match = get_live(ctx, cal.ET, CalendarEntry, blk.id, "id")
                if match.mobility != "flexible":
                    raise validation(f"{where}: {blk.id} is a FIXED entry; plans only manage flexible blocks", "id")
            else:
                for e in unmatched:
                    if e.id not in used and e.title == blk.title and e.start_at == s_utc and e.end_at == e_utc:
                        match = e
                        break
                if match is None and any(links):
                    for e in unmatched:
                        if (
                            e.id not in used and e.status == "planned" and e.title == blk.title
                            and (e.task_id, e.study_topic_id, e.routine_id) == links
                        ):
                            match = e
                            break
            kwargs = {"mobility": "flexible", "title": blk.title, "category": blk.category, "start": blk.start, "end": blk.end}
            for f in ("notes", "task_id", "study_topic_id", "routine_id", "project_id"):
                if getattr(blk, f) is not None:
                    kwargs[f] = getattr(blk, f)
            if match is not None:
                kwargs.update(id=fmt(cal.ET, match.id), version=match.version)
            upsert = cal.EntryUpsert(**kwargs)
            if match is not None:
                used.add(match.id)
            res = cal._apply_entry(ctx, upsert, touched)
            if res["action"] == "created":
                created.append(res["entry"])
            elif res["action"] == "updated":
                updated.append(res["entry"])
            else:
                unchanged += 1
        removed = []
        if plan.mode == "replace":
            now = ctx.now()
            for e in unmatched:
                if e.id in used:
                    continue
                if e.status == "planned" and e.end_at > now:
                    soft_delete(ctx, cal.ET, e, e.title)
                    removed.append({"id": fmt(cal.ET, e.id), "title": e.title, "start": iso(e.start_at, ctx.tz)})
        out.append(
            {
                "date": plan.date.isoformat(),
                "plan": plan_out(row),
                "created": created,
                "updated": updated,
                "removed": removed,
                "unchanged": unchanged,
            }
        )
    cal.validate_conflicts(ctx, touched)
    for item, plan in zip(out, plans):
        day = get_schedule(ctx, plan.date, plan.date)["days"][0]
        item["day"] = day
    return {"plans": out}


def _link_ids(blk: PlanBlock) -> tuple:
    def f(et, v):
        return parse(et, v) if v else None

    return (f("task", blk.task_id), f("study_topic", blk.study_topic_id), f("routine", blk.routine_id))
