"""Calendar entries: fixed events + flexible blocks, recurrence, conflict and fixed-event protection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.crud import Draft, apply_fields, begin, compact, finish, get_live, item_ctx, only_set, soft_delete
from app.core.ctx import Ctx
from app.core.errors import AppError, validation
from app.core.ids import fmt, parse
from app.core.timeutil import UTC, iso, local_midnight, minutes_between, to_utc
from app.domains.audit import service as audit
from app.domains.calendar import recurrence
from app.domains.calendar.models import CalendarEntry
from app.domains.projects.models import Project
from app.domains.routines.models import Routine
from app.domains.study.models import StudyTopic
from app.domains.tasks.models import Task

ET = "calendar_entry"
CATEGORIES = ("meeting", "appointment", "work", "study", "training", "meal", "personal", "rest", "other")
ACTIVE = ("planned", "done")
# Changing any of these on a fixed entry needs explicit confirmation from Claude.
PROTECTED = ("title", "category", "mobility", "all_day", "start_at", "end_at", "rrule")
HORIZON_DAYS = 60


class EntryUpsert(BaseModel):
    """Create (no id) or update (id + version). Only the fields you send are changed.
    To move an entry send only `start` (duration is kept)."""

    id: str | None = Field(None, description="Existing entry id (e.g. 'c12') to update")
    version: int | None = Field(None, description="Required when updating: the version from the last read")
    client_ref: str | None = None
    title: str | None = None
    mobility: Literal["fixed", "flexible"] | None = Field(
        None,
        description="fixed = real commitment (meeting, appointment, class). flexible = a block you planned "
        "that can be moved. Defaults to fixed when creating.",
    )
    category: Literal["meeting", "appointment", "work", "study", "training", "meal", "personal", "rest", "other"] | None = None
    start: datetime | None = Field(None, description="ISO datetime. Without offset = user's local time")
    end: datetime | None = None
    all_day: bool | None = None
    status: Literal["planned", "done", "skipped", "cancelled"] | None = None
    skip_reason: str | None = None
    location: str | None = None
    notes: str | None = None
    task_id: str | None = None
    study_topic_id: str | None = None
    routine_id: str | None = None
    project_id: str | None = None
    rrule: str | None = Field(None, description="Bare RRULE, e.g. FREQ=WEEKLY;BYDAY=TH. start is the first occurrence")
    scope: Literal["this", "all"] = Field(
        "all", description="For recurring entries: 'this' changes one occurrence (needs occurrence_start)"
    )
    occurrence_start: datetime | None = Field(None, description="Start of the occurrence when scope='this'")
    confirm_fixed: bool = Field(
        False,
        description="Set true ONLY when the user explicitly asked in this conversation to change a FIXED entry",
    )
    reason: str | None = Field(None, description="Why a fixed entry is being changed (logged)")


@dataclass
class Occ:
    entry: CalendarEntry
    start: datetime
    end: datetime
    virtual: bool = False  # produced by expanding a recurring master (no row of its own)

    @property
    def active(self) -> bool:
        return self.entry.status in ACTIVE


# --------------------------------------------------------------------------- reading

def occurrences(ctx: Ctx, win_start: datetime, win_end: datetime, *, include_inactive: bool = False) -> list[Occ]:
    base = (CalendarEntry.user_id == ctx.user_id) & CalendarEntry.deleted_at.is_(None)
    plain = ctx.db.scalars(
        select(CalendarEntry).where(
            base, CalendarEntry.rrule.is_(None), CalendarEntry.start_at < win_end, CalendarEntry.end_at > win_start
        )
    ).all()
    masters = ctx.db.scalars(
        select(CalendarEntry).where(
            base, CalendarEntry.rrule.is_not(None), CalendarEntry.series_id.is_(None), CalendarEntry.start_at < win_end
        )
    ).all()
    skipped: set[tuple[int, datetime]] = set()
    if masters:
        exc = ctx.db.scalars(
            select(CalendarEntry).where(
                base,
                CalendarEntry.series_id.in_([m.id for m in masters]),
                CalendarEntry.original_start >= win_start - timedelta(days=40),
                CalendarEntry.original_start < win_end + timedelta(days=1),
            )
        ).all()
        skipped = {(e.series_id, e.original_start) for e in exc}
    out = [Occ(e, e.start_at, e.end_at) for e in plain]
    for m in masters:
        for s, e in recurrence.expand(m.rrule, m.start_at, m.end_at, ctx.tz, win_start, win_end):
            if (m.id, s) not in skipped:
                out.append(Occ(m, s, e, virtual=True))
    if not include_inactive:
        out = [o for o in out if o.active]
    out.sort(key=lambda o: (o.start, o.end, o.entry.id))
    return out


class LinkMaps:
    """Batch-loaded names for the objects entries point to."""

    def __init__(self, ctx: Ctx, entries: list[CalendarEntry]):
        db = ctx.db

        def load(Model, ids, label):
            ids = {i for i in ids if i}
            if not ids:
                return {}
            return {o.id: label(o) for o in db.scalars(select(Model).where(Model.id.in_(ids)))}

        self.tasks = load(Task, (e.task_id for e in entries), lambda o: o.title)
        self.topics = load(StudyTopic, (e.study_topic_id for e in entries), lambda o: o.name)
        self.routines = load(Routine, (e.routine_id for e in entries), lambda o: o.name)
        self.projects = load(Project, (e.project_id for e in entries), lambda o: o.name)


def entry_out(ctx: Ctx, o: Occ, maps: LinkMaps | None = None, *, overlaps: list[str] | None = None) -> dict:
    e = o.entry
    tz = ctx.tz
    d = {
        "id": fmt(ET, e.id),
        "title": e.title,
        "mobility": e.mobility,
        "category": e.category,
        "start": iso(o.start, tz),
        "end": iso(o.end, tz),
        "minutes": minutes_between(o.start, o.end),
        "all_day": e.all_day,
        "status": e.status,
        "skip_reason": e.skip_reason,
        "location": e.location,
        "notes": e.notes,
        "version": e.version,
        "created_by": e.created_by,
    }
    if e.rrule:
        d["recurring"] = True
        d["rrule"] = e.rrule
        if o.virtual:
            d["occurrence_start"] = iso(o.start, tz)
    if e.series_id:
        d["series_id"] = fmt(ET, e.series_id)
        d["occurrence_start"] = iso(e.original_start, tz)
    if maps:
        for key, fk, mp in (
            ("task", e.task_id, maps.tasks),
            ("study_topic", e.study_topic_id, maps.topics),
            ("routine", e.routine_id, maps.routines),
            ("project", e.project_id, maps.projects),
        ):
            if fk and fk in mp:
                d[key] = {"id": fmt({"task": "task", "study_topic": "study_topic", "routine": "routine", "project": "project"}[key], fk), "name": mp[fk]}
    if overlaps:
        d["overlaps_with"] = overlaps
    return compact(d)


# --------------------------------------------------------------------------- writing

def _check_link(ctx: Ctx, et: str, Model, value: str | None, field: str) -> int | None:
    if value is None:
        return None
    return get_live(ctx, et, Model, value, field).id


def _norm_times(ctx: Ctx, start: datetime, end: datetime, all_day: bool) -> tuple[datetime, datetime]:
    s, e = to_utc(start, ctx.tz), to_utc(end, ctx.tz)
    if all_day:
        s = local_midnight(s.astimezone(ctx.tz).date(), ctx.tz)
        e_date = e.astimezone(ctx.tz).date()
        e = local_midnight(e_date, ctx.tz)
        if e <= s:
            e = local_midnight(s.astimezone(ctx.tz).date() + timedelta(days=1), ctx.tz)
        if (e - s) > timedelta(days=62):
            raise validation("All-day entries can span at most 62 days", "end")
    else:
        if e <= s:
            raise validation("end must be after start", "end")
        if (e - s) > timedelta(hours=24):
            raise validation("Timed entries can span at most 24 hours; use all_day for longer ones", "end")
    return s, e


def _locate(ctx: Ctx, item: EntryUpsert) -> tuple[Draft, dict, bool]:
    """Find / create the row to edit. Returns (draft, protected-fields-before-view, from_series)."""
    if item.id and item.scope == "this" and item.occurrence_start is not None:
        master = get_live(ctx, ET, CalendarEntry, item.id)
        if not master.rrule:
            raise validation(f"{item.id} is not a recurring entry; omit scope/occurrence_start", "scope")
        if item.version is not None and item.version != master.version:
            raise AppError(
                "STALE_VERSION", f"{item.id} changed since you read it (current v{master.version}). Re-read and retry.",
                details={"current_version": master.version},
            )
        occ_start = to_utc(item.occurrence_start, ctx.tz)
        if not recurrence.is_occurrence(master.rrule, master.start_at, master.end_at, ctx.tz, occ_start):
            raise validation(
                f"{item.occurrence_start.isoformat()} is not an occurrence of {item.id}", "occurrence_start"
            )
        existing = ctx.db.scalars(
            select(CalendarEntry).where(
                CalendarEntry.user_id == ctx.user_id, CalendarEntry.series_id == master.id,
                CalendarEntry.original_start == occ_start, CalendarEntry.deleted_at.is_(None),
            )
        ).first()
        if existing:
            bv = {k: getattr(existing, k) for k in (*PROTECTED, "status")}
            return Draft(existing, False, audit.snapshot(existing)), bv, False
        dur = master.end_at - master.start_at
        row = CalendarEntry(
            user_id=ctx.user_id, created_by=ctx.actor, updated_by=ctx.actor, title=master.title,
            mobility=master.mobility, category=master.category, start_at=occ_start, end_at=occ_start + dur,
            all_day=master.all_day, status="planned", location=master.location, notes=master.notes,
            task_id=master.task_id, study_topic_id=master.study_topic_id, routine_id=master.routine_id,
            project_id=master.project_id, rrule=None, series_id=master.id, original_start=occ_start,
        )
        bv = {k: getattr(row, k) for k in (*PROTECTED, "status")}
        bv["mobility"] = master.mobility
        return Draft(row, True, None), bv, True
    d = begin(
        ctx, ET, CalendarEntry, id=item.id, version=item.version, client_ref=item.client_ref,
        defaults={"mobility": "fixed", "category": "other", "status": "planned", "all_day": False},
    )
    bv = None if d.created else {k: getattr(d.obj, k) for k in (*PROTECTED, "status")}
    return d, bv or {}, False


def _apply_entry(ctx: Ctx, item: EntryUpsert, touched: list[CalendarEntry]) -> dict:
    d, bv, from_series = _locate(ctx, item)
    e: CalendarEntry = d.obj
    created = d.created
    sent = item.model_fields_set
    brand_new = created and not from_series

    vals = only_set(item, "title", "mobility", "category", "all_day", "status", "skip_reason", "location", "notes")
    for k in ("title", "mobility", "category", "all_day", "status"):
        if k in vals and vals[k] is None:
            raise validation(f"{k} cannot be null", k)
    if "title" in vals:
        vals["title"] = vals["title"].strip()
        if not vals["title"]:
            raise validation("title cannot be empty", "title")
    if brand_new:
        if not vals.get("title"):
            raise validation("title is required to create an entry", "title")
        if item.start is None:
            raise validation("start is required to create an entry", "start")
    for fld, et, Model in (
        ("task_id", "task", Task), ("study_topic_id", "study_topic", StudyTopic),
        ("routine_id", "routine", Routine), ("project_id", "project", Project),
    ):
        if fld in sent:
            vals[fld] = _check_link(ctx, et, Model, getattr(item, fld), fld)

    apply_fields(e, vals)

    # times
    all_day = e.all_day
    if (
        e.rrule and not from_series and item.scope == "all" and item.occurrence_start is not None
        and item.start is not None and not brand_new
    ):
        # Editing "all occurrences" from the view of one occurrence: apply the *shift* to the series anchor,
        # keeping the series' first date (otherwise past occurrences would vanish).
        occ = to_utc(item.occurrence_start, ctx.tz).astimezone(ctx.tz).replace(tzinfo=None)
        new_local = to_utc(item.start, ctx.tz).astimezone(ctx.tz).replace(tzinfo=None)
        anchor = e.start_at.astimezone(ctx.tz).replace(tzinfo=None) + (new_local - occ)
        new_end = item.end
        item = item.model_copy(update={"start": anchor, "end": (anchor + (item.end - item.start)) if new_end else None})
        sent = sent | {"start"} | ({"end"} if new_end else set())
    if "start" in sent or "end" in sent or "all_day" in sent or brand_new:
        if item.start is not None:
            start = to_utc(item.start, ctx.tz)
        else:
            start = e.start_at
        if item.end is not None:
            end = to_utc(item.end, ctx.tz)
        elif start is not None and e.start_at is not None and e.end_at is not None and not brand_new:
            end = start + (e.end_at - e.start_at)  # keep duration when only start is sent
        elif all_day:
            end = start + timedelta(days=1)
        else:
            raise validation("end is required to create a timed entry", "end")
        e.start_at, e.end_at = _norm_times(ctx, start, end, all_day)

    if "rrule" in sent:
        if item.rrule is None:
            e.rrule = None
        else:
            if e.series_id:
                raise validation("A single occurrence cannot have its own rrule", "rrule")
            e.rrule = recurrence.normalize_rrule(item.rrule)
            if (e.end_at - e.start_at) > timedelta(hours=24) and not e.all_day:
                raise validation("Recurring timed entries must be 24h or shorter", "end")

    if e.category not in CATEGORIES:
        raise validation(f"Unknown category '{e.category}'", "category")
    if e.status != "skipped":
        e.skip_reason = None

    # ---- fixed-entry protection (Claude must confirm explicitly) ----
    label = e.title
    if ctx.strict and bv and bv.get("mobility") == "fixed":
        changed = [k for k in PROTECTED if bv.get(k) != getattr(e, k)]
        if e.status == "cancelled" and bv.get("status") != "cancelled":
            changed.append("status=cancelled")
        if changed:
            if not (item.confirm_fixed and (item.reason or "").strip()):
                raise AppError(
                    "CONFIRMATION_REQUIRED",
                    f"'{e.title}' is a FIXED entry; changing {', '.join(changed)} needs the user's explicit request.",
                    hint="If the user explicitly asked for this change, resend with confirm_fixed=true and a short "
                    "reason. Otherwise leave it as is, or move a flexible block instead.",
                )
            label = f"{e.title} (fixed changed: {item.reason.strip()})"

    # ---- past protection (Claude can't schedule into the past) ----
    time_changed = bool(bv) and (bv.get("start_at") != e.start_at or bv.get("end_at") != e.end_at)
    if ctx.strict and not e.rrule and e.status == "planned" and (brand_new or time_changed) and e.end_at <= ctx.now():
        raise AppError(
            "PAST_DATE",
            f"'{e.title}' ends in the past ({iso(e.end_at, ctx.tz)}); planned entries must end in the future.",
            hint="To log something that already happened, create it with status 'done' or 'skipped'.",
        )

    prev_status = bv.get("status") if bv else None
    action = finish(ctx, d, ET, label)
    if e.status in ACTIVE and action != "unchanged":
        touched.append(e)
    # a finished study block becomes a study session
    if e.status == "done" and prev_status != "done" and e.study_topic_id:
        from app.domains.study.service import auto_session_from_entry

        auto_session_from_entry(ctx, e)
    return {"action": action, "entry": entry_out(ctx, Occ(e, e.start_at, e.end_at), LinkMaps(ctx, [e]))}


def _free_hint(ctx: Ctx, day: date) -> str | None:
    from app.domains.planning.service import free_windows_for_day

    wins = free_windows_for_day(ctx, day)
    if not wins:
        return None
    return "Free windows that day: " + ", ".join(f"{w['start'][11:16]}-{w['end'][11:16]}" for w in wins[:5])


def validate_conflicts(ctx: Ctx, touched: list[CalendarEntry]) -> None:
    """After a batch is applied, check the final state. Strict mode raises; manual mode warns."""
    seen_pairs: set[tuple[int, int]] = set()
    errors: list[dict] = []
    code = None
    first_day: date | None = None
    for e in touched:
        if e.deleted_at is not None or e.status not in ACTIVE or e.all_day:
            continue
        now = ctx.now()
        if e.rrule:
            win_s, win_e = max(e.start_at, now), max(e.start_at, now) + timedelta(days=HORIZON_DAYS)
            mine = recurrence.expand(e.rrule, e.start_at, e.end_at, ctx.tz, win_s, win_e)
        else:
            win_s, win_e = e.start_at, e.end_at
            mine = [(e.start_at, e.end_at)]
        if not mine:
            continue
        others = [
            o for o in occurrences(ctx, win_s, win_e)
            if not o.entry.all_day and o.entry.id != e.id and o.entry.series_id != e.id
        ]
        for s, en in mine:
            for o in others:
                if not (o.start < en and o.end > s):
                    continue
                pair = tuple(sorted((e.id, o.entry.id)))
                other_fixed = o.entry.mobility == "fixed"
                if e.mobility == "fixed" and not other_fixed:
                    ctx.warn(
                        "OVERLAPS_FLEXIBLE",
                        f"Fixed '{e.title}' now overlaps flexible '{o.entry.title}' "
                        f"({iso(o.start, ctx.tz)}); move the flexible block.",
                        entry=fmt(ET, o.entry.id),
                    )
                    continue
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)
                c = "CONFLICT_FIXED_EVENT" if (other_fixed or e.mobility == "fixed") else "CONFLICT_OVERLAP"
                if not ctx.strict:
                    ctx.warn("OVERLAP", f"'{e.title}' overlaps '{o.entry.title}' at {iso(s, ctx.tz)}",
                             entry=fmt(ET, o.entry.id))
                    continue
                code = code if code == "CONFLICT_FIXED_EVENT" else c
                first_day = first_day or s.astimezone(ctx.tz).date()
                errors.append(
                    {
                        "with": fmt(ET, e.id),
                        "id": fmt(ET, o.entry.id),
                        "title": o.entry.title,
                        "mobility": o.entry.mobility,
                        "start": iso(o.start, ctx.tz),
                        "end": iso(o.end, ctx.tz),
                    }
                )
    if errors:
        mine_titles = sorted({next(x.title for x in touched if fmt(ET, x.id) == c["with"]) for c in errors})
        raise AppError(
            code or "CONFLICT_OVERLAP",
            f"Time conflict: {', '.join(mine_titles)} overlaps existing entries.",
            conflicts=errors[:6],
            hint=_free_hint(ctx, first_day) if first_day else None,
        )


def save_entries(ctx: Ctx, items: list[EntryUpsert]) -> dict:
    results, touched = [], []
    for i, item in enumerate(items):
        with item_ctx(i):
            results.append(_apply_entry(ctx, item, touched))
    validate_conflicts(ctx, touched)
    return {"results": results}


def delete_entry(ctx: Ctx, ident: str, *, scope: str = "all", occurrence_start: datetime | None = None,
                 confirm_fixed: bool = False, reason: str | None = None) -> dict:
    e = get_live(ctx, ET, CalendarEntry, ident)
    if e.rrule and scope == "this":
        if occurrence_start is None:
            raise validation("occurrence_start is required to delete a single occurrence", "occurrence_start")
        res = save_entries(
            ctx,
            [EntryUpsert(id=ident, scope="this", occurrence_start=occurrence_start, status="cancelled",
                         confirm_fixed=confirm_fixed, reason=reason)],
        )
        return {"cancelled_occurrence": res["results"][0]["entry"]["id"]}
    if ctx.strict and e.mobility == "fixed" and not (confirm_fixed and (reason or "").strip()):
        raise AppError(
            "CONFIRMATION_REQUIRED",
            f"'{e.title}' is a FIXED entry; deleting it needs the user's explicit request.",
            hint="If the user explicitly asked to delete it, resend with confirm_fixed=true and a short reason.",
        )
    n = 0
    if e.rrule:
        for x in ctx.db.scalars(
            select(CalendarEntry).where(
                CalendarEntry.user_id == ctx.user_id, CalendarEntry.series_id == e.id, CalendarEntry.deleted_at.is_(None)
            )
        ):
            soft_delete(ctx, ET, x, x.title)
            n += 1
    soft_delete(ctx, ET, e, e.title if not reason else f"{e.title} (deleted: {reason.strip()})")
    return {"deleted_occurrence_overrides": n}


def parse_entry_id(value: str) -> int:
    return parse(ET, value)
