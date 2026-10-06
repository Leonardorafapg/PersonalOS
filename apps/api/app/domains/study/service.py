"""Study roadmap: a tree of topics (what to learn) + sessions (what was actually studied).

The roadmap is deliberately decoupled from the calendar: deciding *when* to study is Claude's job.
The backend only provides facts: rolled-up progress, unmet prerequisites and which topics are available.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.crud import Draft, apply_fields, begin, compact, finish, get_live, item_ctx, only_set, soft_delete
from app.core.ctx import Ctx
from app.core.errors import AppError, validation
from app.core.ids import fmt, parse
from app.core.timeutil import iso, minutes_between
from app.domains.audit import service as audit
from app.domains.calendar.models import CalendarEntry
from app.domains.study.models import StudySession, StudyTopic

ET = "study_topic"
ES = "study_session"
STATUSES = ("not_started", "in_progress", "done", "paused", "skipped")
MAX_DEPTH = 8


class Resource(BaseModel):
    title: str
    url: str | None = None
    kind: Literal["video", "book", "doc", "course", "article", "repo", "other"] = "other"
    done: bool = False


class StudyTopicUpsert(BaseModel):
    """Create (no id) or update (id + version) a roadmap node. `children` lets you import a whole tree at once."""

    id: str | None = Field(None, description="Existing topic id (e.g. 's12') to update")
    version: int | None = Field(None, description="Required when updating")
    client_ref: str | None = Field(None, description="Stable key (e.g. 'python.async'); re-importing updates instead of duplicating")
    ref: str | None = Field(None, description="Local alias valid only inside this call, usable in `prerequisites`")
    parent_id: str | None = Field(None, description="Parent topic id; omit for a root (area)")
    kind: Literal["area", "topic"] | None = None
    name: str | None = None
    description: str | None = None
    status: Literal["not_started", "in_progress", "done", "paused", "skipped"] | None = None
    progress: int | None = Field(None, ge=0, le=100, description="0-100, only for leaf topics")
    sort_order: int | None = None
    difficulty: int | None = Field(None, ge=1, le=5)
    estimated_minutes: int | None = Field(None, ge=1)
    notes: str | None = None
    resources: list[Resource] | None = Field(None, description="Replaces the whole resource list when sent")
    prerequisites: list[str] | None = Field(
        None, description="Topics that should be done first: ids ('s3'), client_refs or `ref`s from this call"
    )
    children: list["StudyTopicUpsert"] = Field(default_factory=list)


StudyTopicUpsert.model_rebuild()


# --------------------------------------------------------------------------- tree + rollups

class Node:
    __slots__ = ("t", "children", "leaf", "status", "progress", "leaves", "leaves_done", "minutes", "last", "blocked_by")

    def __init__(self, t: StudyTopic):
        self.t = t
        self.children: list[Node] = []
        self.leaf = True
        self.status = t.status
        self.progress = t.progress
        self.leaves = 0
        self.leaves_done = 0
        self.minutes = 0
        self.last: date | None = None
        self.blocked_by: list[int] = []


def load_tree(ctx: Ctx) -> tuple[dict[int, Node], list[Node]]:
    topics = ctx.db.scalars(
        select(StudyTopic).where(StudyTopic.user_id == ctx.user_id, StudyTopic.deleted_at.is_(None))
    ).all()
    nodes = {t.id: Node(t) for t in topics}
    roots: list[Node] = []
    for n in nodes.values():
        p = nodes.get(n.t.parent_id) if n.t.parent_id else None
        (p.children if p else roots).append(n)
    key = lambda n: (n.t.sort_order, n.t.id)  # noqa: E731
    for n in nodes.values():
        n.children.sort(key=key)
        n.leaf = not n.children
    roots.sort(key=key)
    sess = {
        tid: (mins, last)
        for tid, mins, last in ctx.db.execute(
            select(StudySession.topic_id, func.sum(StudySession.minutes), func.max(StudySession.session_date))
            .where(StudySession.user_id == ctx.user_id, StudySession.deleted_at.is_(None))
            .group_by(StudySession.topic_id)
        )
    }

    def roll(n: Node) -> None:
        mins, last = sess.get(n.t.id, (0, None))
        n.minutes, n.last = int(mins or 0), last
        if n.leaf:
            counted = n.status != "skipped"
            n.leaves = 1 if counted else 0
            n.leaves_done = 1 if n.status == "done" else 0
            return
        total_progress, any_active, all_skipped = 0, False, True
        for c in n.children:
            roll(c)
            n.leaves += c.leaves
            n.leaves_done += c.leaves_done
            n.minutes += c.minutes
            if c.last and (n.last is None or c.last > n.last):
                n.last = c.last
            total_progress += c.progress * c.leaves
            any_active = any_active or c.status in ("in_progress", "done") or c.progress > 0
            all_skipped = all_skipped and c.status == "skipped"
        n.progress = round(total_progress / n.leaves) if n.leaves else 0
        if all_skipped:
            n.status = "skipped"
        elif n.leaves and n.leaves_done == n.leaves:
            n.status = "done"
        elif any_active:
            n.status = "in_progress"
        else:
            n.status = "not_started"

    for r in roots:
        roll(r)
    for n in nodes.values():
        n.blocked_by = [
            pid for pid in (n.t.prerequisite_ids or [])
            if pid in nodes and nodes[pid].status not in ("done", "skipped")
        ]
    return nodes, roots


def _path(nodes: dict[int, Node], n: Node) -> str:
    names, cur = [], n
    while cur:
        names.append(cur.t.name)
        cur = nodes.get(cur.t.parent_id) if cur.t.parent_id else None
    return " › ".join(reversed(names))


def node_out(ctx: Ctx, nodes: dict[int, Node], n: Node, depth: int, *, only_open: bool = False) -> dict:
    t = n.t
    d: dict = {
        "id": fmt(ET, t.id),
        "name": t.name,
        "kind": t.kind,
        "status": n.status,
        "progress": n.progress,
        "difficulty": t.difficulty,
        "estimated_minutes": t.estimated_minutes,
        "minutes_spent": n.minutes or None,
        "last_studied": n.last.isoformat() if n.last else None,
        "prerequisites": [fmt(ET, i) for i in (t.prerequisite_ids or []) if i in nodes],
        "blocked_by": [fmt(ET, i) for i in n.blocked_by],
        "version": t.version,
    }
    if not n.leaf:
        d["leaves"] = f"{n.leaves_done}/{n.leaves}"
        kids = [c for c in n.children if not (only_open and c.status in ("done", "skipped"))]
        if depth > 0:
            d["children"] = [node_out(ctx, nodes, c, depth - 1, only_open=only_open) for c in kids]
        else:
            d["children_count"] = len(n.children)
    return compact(d)


def study_overview(nodes: dict[int, Node]) -> dict:
    leaves = [n for n in nodes.values() if n.leaf and n.status != "skipped"]
    total = len(leaves)
    return {
        "topics": total,
        "done": sum(1 for n in leaves if n.status == "done"),
        "in_progress": sum(1 for n in leaves if n.status == "in_progress"),
        "progress": round(sum(n.progress for n in leaves) / total) if total else 0,
    }


def _dfs(roots: list[Node]):
    for r in roots:
        yield r
        yield from _dfs(r.children)


def available_topics(ctx: Ctx, nodes: dict[int, Node], roots: list[Node], limit: int | None = None) -> list[dict]:
    out = []
    for n in _dfs(roots):
        if not n.leaf or n.status not in ("not_started", "in_progress") or n.blocked_by:
            continue
        # skip leaves living under a paused / skipped ancestor
        anc, blocked = nodes.get(n.t.parent_id), False
        while anc:
            if anc.t.status in ("paused", "skipped"):
                blocked = True
                break
            anc = nodes.get(anc.t.parent_id) if anc.t.parent_id else None
        if blocked:
            continue
        out.append(
            compact(
                {
                    "id": fmt(ET, n.t.id),
                    "path": _path(nodes, n),
                    "status": n.status,
                    "progress": n.progress,
                    "difficulty": n.t.difficulty,
                    "estimated_minutes": n.t.estimated_minutes,
                    "minutes_spent": n.minutes or None,
                    "last_studied": n.last.isoformat() if n.last else None,
                    "version": n.t.version,
                }
            )
        )
        if limit and len(out) >= limit:
            break
    return out


def get_study(ctx: Ctx, topic_id: str | None = None, depth: int = 2, only_available: bool = False,
              only_open: bool = False, limit: int = 60) -> dict:
    nodes, roots = load_tree(ctx)
    overview = study_overview(nodes)
    if only_available:
        av = available_topics(ctx, nodes, roots, limit)
        return {"overview": overview, "available": av, "count": len(av)}
    if topic_id:
        tid = parse(ET, topic_id, "topic_id")
        n = nodes.get(tid)
        if n is None:
            raise validation(f"Topic {topic_id} not found", "topic_id")
        t = n.t
        sessions = ctx.db.scalars(
            select(StudySession)
            .where(StudySession.user_id == ctx.user_id, StudySession.topic_id == tid, StudySession.deleted_at.is_(None))
            .order_by(StudySession.session_date.desc(), StudySession.id.desc())
            .limit(10)
        ).all()
        dependents = [fmt(ET, o.t.id) for o in nodes.values() if tid in (o.t.prerequisite_ids or [])]
        detail = node_out(ctx, nodes, n, depth, only_open=only_open)
        detail.update(
            compact(
                {
                    "parent_id": fmt(ET, t.parent_id),
                    "path": _path(nodes, n),
                    "description": t.description,
                    "notes": t.notes,
                    "resources": t.resources,
                    "required_by": dependents,
                    "recent_sessions": [
                        compact({"id": fmt(ES, s.id), "date": s.session_date.isoformat(), "minutes": s.minutes,
                                 "notes": s.notes}) for s in sessions
                    ],
                }
            )
        )
        return {"topic": detail}
    return {"overview": overview, "roots": [node_out(ctx, nodes, r, depth, only_open=only_open) for r in roots]}


# --------------------------------------------------------------------------- writing

def _next_sort(ctx: Ctx, parent_id: int | None) -> int:
    q = select(func.max(StudyTopic.sort_order)).where(
        StudyTopic.user_id == ctx.user_id, StudyTopic.deleted_at.is_(None),
        StudyTopic.parent_id == parent_id if parent_id else StudyTopic.parent_id.is_(None),
    )
    m = ctx.db.scalar(q)
    return 0 if m is None else m + 1


def _coherent(t: StudyTopic, sent: set[str], prev_status: str | None) -> None:
    """Keep status and progress consistent on leaf topics."""
    if "status" in sent and t.status == "done":
        t.progress = 100
    elif "progress" in sent:
        if t.progress >= 100:
            t.status = "done"
        elif t.status == "done" or (t.status == "not_started" and t.progress > 0):
            t.status = "in_progress"
    elif "status" in sent and t.status == "not_started" and prev_status in ("done", "in_progress"):
        t.progress = 0
    elif "status" in sent and t.status == "in_progress" and prev_status == "done":
        t.progress = min(t.progress, 90)


def _would_cycle_parent(ctx: Ctx, t: StudyTopic, new_parent: int) -> bool:
    cur = new_parent
    for _ in range(MAX_DEPTH * 4):
        if cur == t.id:
            return True
        p = ctx.db.get(StudyTopic, cur)
        if p is None or p.parent_id is None:
            return False
        cur = p.parent_id
    return True


def _depth(ctx: Ctx, parent_id: int | None) -> int:
    d, cur = 0, parent_id
    while cur and d <= MAX_DEPTH + 2:
        p = ctx.db.get(StudyTopic, cur)
        if p is None:
            break
        d += 1
        cur = p.parent_id
    return d


def _save_node(ctx: Ctx, node: StudyTopicUpsert, parent_override: int | None, has_parent_override: bool,
               refs: dict[str, int], drafts: list, prereq_todo: list, results: list, path: str) -> None:
    d = begin(
        ctx, ET, StudyTopic, id=node.id, version=node.version, client_ref=node.client_ref,
        defaults={"kind": "topic", "status": "not_started", "progress": 0, "sort_order": 0,
                  "resources": [], "prerequisite_ids": []},
    )
    t: StudyTopic = d.obj
    sent = node.model_fields_set
    prev_status = None if d.created else t.status
    vals = only_set(node, "kind", "name", "description", "status", "progress", "sort_order", "difficulty",
                    "estimated_minutes", "notes")
    for k in ("kind", "name", "status", "progress"):
        if k in vals and vals[k] is None:
            raise validation(f"{k} cannot be null", k)
    if "name" in vals:
        vals["name"] = vals["name"].strip()
        if not vals["name"]:
            raise validation("name cannot be empty", "name")
    if d.created and not vals.get("name"):
        raise validation(f"{path}: name is required to create a topic", "name")
    apply_fields(t, vals)

    # parent
    if has_parent_override:
        new_parent: int | None = parent_override
        set_parent = True
    elif "parent_id" in sent:
        new_parent = get_live(ctx, ET, StudyTopic, node.parent_id, "parent_id").id if node.parent_id else None
        set_parent = True
    else:
        new_parent, set_parent = None, False
    if set_parent:
        if new_parent and not d.created and _would_cycle_parent(ctx, t, new_parent):
            raise validation("A topic cannot be moved under itself or its own descendants", "parent_id")
        if _depth(ctx, new_parent) >= MAX_DEPTH:
            raise validation(f"Roadmap depth is limited to {MAX_DEPTH} levels", "parent_id")
        t.parent_id = new_parent
    if d.created and "sort_order" not in sent:
        t.sort_order = _next_sort(ctx, t.parent_id)

    if "resources" in sent and node.resources is not None:
        t.resources = [r.model_dump() for r in node.resources]
    eff_sent = {k for k in sent if k in ("status", "progress")}
    _coherent(t, eff_sent, prev_status)

    if d.created:  # need an id now for children/refs; audit is written after prerequisites resolve
        ctx.db.add(t)
        ctx.db.flush()
    drafts.append(d)
    if node.ref:
        refs[node.ref] = t.id
    if node.client_ref:
        refs.setdefault(node.client_ref, t.id)
    if node.prerequisites is not None:
        prereq_todo.append((t, node.prerequisites))
    results.append((d, node))
    for child in node.children:
        _save_node(ctx, child, t.id, True, refs, drafts, prereq_todo, results, f"{path}/{t.name}")


def _resolve_prereq(ctx: Ctx, token: str, refs: dict[str, int]) -> int:
    if token in refs:
        return refs[token]
    try:
        return get_live(ctx, ET, StudyTopic, token, "prerequisites").id
    except AppError:
        pass
    row = ctx.db.scalars(
        select(StudyTopic).where(
            StudyTopic.user_id == ctx.user_id, StudyTopic.client_ref == token, StudyTopic.deleted_at.is_(None)
        )
    ).first()
    if row:
        return row.id
    raise validation(f"Unknown prerequisite '{token}' (use a topic id, client_ref or ref from this call)", "prerequisites")


def _reaches(start: int, target: int, graph: dict[int, list[int]]) -> bool:
    seen, stack = set(), [start]
    while stack:
        cur = stack.pop()
        if cur == target:
            return True
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(graph.get(cur, []))
    return False


def save_topics(ctx: Ctx, items: list[StudyTopicUpsert]) -> dict:
    refs: dict[str, int] = {}
    drafts: list[Draft] = []
    prereq_todo: list[tuple[StudyTopic, list[str]]] = []
    results: list[tuple[Draft, StudyTopicUpsert]] = []
    for i, item in enumerate(items):
        with item_ctx(i):
            _save_node(ctx, item, None, False, refs, drafts, prereq_todo, results, "")
    # prerequisites (after every node of the call exists)
    graph = {
        t.id: list(t.prerequisite_ids or [])
        for t in ctx.db.scalars(
            select(StudyTopic).where(StudyTopic.user_id == ctx.user_id, StudyTopic.deleted_at.is_(None))
        )
    }
    for t, tokens in prereq_todo:
        ids = []
        for tok in tokens:
            pid = _resolve_prereq(ctx, tok, refs)
            if pid == t.id:
                raise validation(f"'{t.name}' cannot be its own prerequisite", "prerequisites")
            if pid not in ids:
                ids.append(pid)
        graph[t.id] = ids
        for pid in ids:
            if _reaches(pid, t.id, graph):
                raise validation(f"Prerequisite cycle: '{t.name}' ↔ {fmt(ET, pid)}", "prerequisites")
        t.prerequisite_ids = ids
    out = []
    for d, node in results:
        action = finish(ctx, d, ET, d.obj.name)
        out.append({"action": action, "id": fmt(ET, d.obj.id), "name": d.obj.name, "version": d.obj.version})
    nodes, roots = load_tree(ctx)
    return {"results": out, "count": len(out), "overview": study_overview(nodes)}


def _descendants(ctx: Ctx, t: StudyTopic) -> list[StudyTopic]:
    out, frontier = [t], [t.id]
    while frontier:
        kids = ctx.db.scalars(
            select(StudyTopic).where(
                StudyTopic.user_id == ctx.user_id, StudyTopic.parent_id.in_(frontier), StudyTopic.deleted_at.is_(None)
            )
        ).all()
        out.extend(kids)
        frontier = [k.id for k in kids]
    return out


def delete_topic(ctx: Ctx, t: StudyTopic) -> dict:
    subtree = _descendants(ctx, t)
    ids = {x.id for x in subtree}
    # drop prerequisite references from topics outside the subtree
    for o in ctx.db.scalars(
        select(StudyTopic).where(StudyTopic.user_id == ctx.user_id, StudyTopic.deleted_at.is_(None))
    ):
        if o.id not in ids and any(p in ids for p in (o.prerequisite_ids or [])):
            d = Draft(o, False, audit.snapshot(o))
            o.prerequisite_ids = [p for p in o.prerequisite_ids if p not in ids]
            finish(ctx, d, ET, o.name)
    for e in ctx.db.scalars(
        select(CalendarEntry).where(
            CalendarEntry.user_id == ctx.user_id, CalendarEntry.study_topic_id.in_(ids), CalendarEntry.deleted_at.is_(None)
        )
    ):
        d = Draft(e, False, audit.snapshot(e))
        e.study_topic_id = None
        finish(ctx, d, "calendar_entry", e.title)
    n_sessions = 0
    for s in ctx.db.scalars(
        select(StudySession).where(
            StudySession.user_id == ctx.user_id, StudySession.topic_id.in_(ids), StudySession.deleted_at.is_(None)
        )
    ):
        soft_delete(ctx, ES, s, f"sessão {s.session_date}")
        n_sessions += 1
    for x in reversed(subtree):
        soft_delete(ctx, ET, x, x.name)
    return {"deleted_topics": len(subtree), "deleted_sessions": n_sessions}


# --------------------------------------------------------------------------- sessions

def auto_session_from_entry(ctx: Ctx, e: CalendarEntry) -> None:
    """A finished study block counts as a study session (unless one already references it)."""
    topic = ctx.db.get(StudyTopic, e.study_topic_id)
    if topic is None or topic.deleted_at is not None or topic.user_id != ctx.user_id:
        return
    exists = ctx.db.scalars(
        select(StudySession).where(
            StudySession.user_id == ctx.user_id, StudySession.entry_id == e.id, StudySession.deleted_at.is_(None)
        )
    ).first()
    if exists:
        return
    _create_session(ctx, topic, max(1, minutes_between(e.start_at, e.end_at)),
                    e.start_at.astimezone(ctx.tz).date(), None, e.id, None, None)


def _create_session(ctx: Ctx, topic: StudyTopic, minutes: int, day: date, notes: str | None, entry_id: int | None,
                    progress: int | None, status: str | None) -> StudySession:
    s = StudySession(
        user_id=ctx.user_id, created_by=ctx.actor, updated_by=ctx.actor, topic_id=topic.id, session_date=day,
        minutes=minutes, notes=notes, entry_id=entry_id,
    )
    ctx.db.add(s)
    ctx.db.flush()
    audit.created(ctx, ES, s, f"{topic.name} · {minutes}min")
    d = Draft(topic, False, audit.snapshot(topic))
    sent = set()
    prev = topic.status
    if progress is not None:
        topic.progress = progress
        sent.add("progress")
    if status is not None:
        topic.status = status
        sent.add("status")
    if topic.status == "not_started":
        topic.status = "in_progress"
    _coherent(topic, sent, prev)
    finish(ctx, d, ET, topic.name)
    return s


def log_study(ctx: Ctx, topic_id: str, minutes: int, day: date | None = None, notes: str | None = None,
              progress: int | None = None, status: str | None = None, entry_id: str | None = None,
              mark_entry_done: bool = False) -> dict:
    topic = get_live(ctx, ET, StudyTopic, topic_id, "topic_id")
    if minutes < 1 or minutes > 1440:
        raise validation("minutes must be between 1 and 1440", "minutes")
    if status is not None and status not in STATUSES:
        raise validation(f"status must be one of {STATUSES}", "status")
    if progress is not None and not 0 <= progress <= 100:
        raise validation("progress must be 0..100", "progress")
    has_children = ctx.db.scalars(
        select(StudyTopic.id).where(
            StudyTopic.user_id == ctx.user_id, StudyTopic.parent_id == topic.id, StudyTopic.deleted_at.is_(None)
        ).limit(1)
    ).first()
    if has_children and (progress is not None or status is not None):
        raise validation(
            "Progress/status are only set on leaf topics; this one has children. Log against a child topic.",
            "topic_id",
        )
    entry = None
    if entry_id:
        entry = get_live(ctx, "calendar_entry", CalendarEntry, entry_id, "entry_id")
    if day is None:
        day = entry.start_at.astimezone(ctx.tz).date() if entry else ctx.today()
    s = _create_session(ctx, topic, minutes, day, notes, entry.id if entry else None, progress, status)
    if entry is not None and mark_entry_done and entry.status != "done":
        from app.domains.calendar import service as cal

        cal.save_entries(ctx, [cal.EntryUpsert(id=fmt("calendar_entry", entry.id), version=entry.version, status="done")])
    nodes, _ = load_tree(ctx)
    return {
        "session": compact({"id": fmt(ES, s.id), "date": s.session_date.isoformat(), "minutes": s.minutes,
                            "notes": s.notes}),
        "topic": node_out(ctx, nodes, nodes[topic.id], 0),
    }
