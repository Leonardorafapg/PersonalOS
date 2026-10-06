"""Domain behaviour exercised through the REST API (manual actor) and MCP (claude actor)."""

from tests.conftest import mcp_call

TZ = "-03:00"


def t(day, hm):
    return f"2026-10-{day:02d}T{hm}:00"


def entry(title, day, s, e, **kw):
    return {"title": title, "start": t(day, s), "end": t(day, e), **kw}


# ------------------------------------------------------------------ tasks
def test_task_lifecycle_versions_and_completed_at(client):
    r = client.post("/tasks", json={"title": "Corrigir webhook", "priority": "high", "due_date": "2026-10-09"})
    assert r.status_code == 200, r.text
    task = r.json()["data"]["task"]
    assert task["status"] == "todo" and task["created_by"] == "manual" and task["id"].startswith("t")
    # stale write is rejected
    bad = client.patch(f"/tasks/{task['id']}", json={"title": "x", "version": 99})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "STALE_VERSION"
    missing = client.patch(f"/tasks/{task['id']}", json={"title": "x"})
    assert missing.status_code == 422
    ok = client.patch(f"/tasks/{task['id']}", json={"status": "done", "version": task["version"]})
    done = ok.json()["data"]["task"]
    assert done["status"] == "done" and "completed_at" in done and done["version"] == 2
    # idempotent: same patch again is a no-op (no version bump)
    again = client.patch(f"/tasks/{task['id']}", json={"status": "done", "version": 2})
    assert again.json()["data"]["action"] == "unchanged" and again.json()["data"]["task"]["version"] == 2
    reopened = client.patch(f"/tasks/{task['id']}", json={"status": "todo", "version": 2}).json()["data"]["task"]
    assert "completed_at" not in reopened


def test_tasks_filters_projects_and_overdue(client):
    p = client.post("/projects", json={"name": "Faelo", "area": "work"}).json()["data"]["project"]
    for title, due in (("a", "2026-10-01"), ("b", "2026-10-20"), ("c", None)):
        client.post("/tasks", json={"title": title, "due_date": due, "project_id": p["id"]})
    lst = client.get("/tasks", params={"overdue": True}).json()["data"]["tasks"]
    assert [x["title"] for x in lst] == ["a"] and lst[0]["overdue"] and lst[0]["project_name"] == "Faelo"
    allp = client.get(f"/projects/{p['id']}").json()["data"]["project"]
    assert allp["open_tasks"] == 3 and allp["overdue_tasks"] == 1 and len(allp["tasks"]) == 3
    # client_ref makes creation idempotent
    a = client.post("/tasks", json={"title": "z", "client_ref": "k1"}).json()["data"]
    b = client.post("/tasks", json={"title": "z", "client_ref": "k1"}).json()["data"]
    assert a["task"]["id"] == b["task"]["id"] and b["action"] == "unchanged"


def test_batch_is_atomic(client):
    env = mcp_call(client, "save_tasks", {"items": [{"title": "ok 1"}, {"title": ""}]})
    assert env["ok"] is False and env["error"]["code"] == "VALIDATION"
    assert "items[1]" in env["error"]["message"]
    assert client.get("/tasks").json()["data"]["tasks"] == []


# ------------------------------------------------------------------ calendar
def test_fixed_vs_flexible_conflict_rules_for_claude(client):
    meeting = mcp_call(client, "save_calendar_entries",
                       {"items": [entry("Reunião", 7, "10:00", "11:00", category="meeting")]}, expect_ok=True)
    mid = meeting["data"]["results"][0]["entry"]
    assert mid["mobility"] == "fixed" and mid["start"] == "2026-10-07T10:00-03:00" and mid["created_by"] == "claude"
    # flexible block over a fixed event -> rejected with conflicts + free-window hint
    bad = mcp_call(client, "save_calendar_entries",
                   {"items": [entry("Estudar", 7, "09:30", "10:30", mobility="flexible", category="study")]})
    assert bad["error"]["code"] == "CONFLICT_FIXED_EVENT"
    assert bad["error"]["conflicts"][0]["id"] == mid["id"] and "Free windows" in bad["error"]["hint"]
    # nothing was written
    day = client.get("/schedule", params={"start": "2026-10-07", "end": "2026-10-07"}).json()["data"]["days"][0]
    assert [e["title"] for e in day["entries"]] == ["Reunião"]
    # free windows: today is Wednesday, now 08:00, wake 07:00, sleep 23:00 -> 08:00-10:00 and 11:00-23:00
    assert [(w["start"][11:16], w["end"][11:16]) for w in day["free_windows"]] == [("08:00", "10:00"), ("11:00", "23:00")]
    # past is protected
    past = mcp_call(client, "save_calendar_entries",
                    {"items": [entry("Ontem", 6, "10:00", "11:00", mobility="flexible")]})
    assert past["error"]["code"] == "PAST_DATE"
    # ... unless logging what happened
    logged = mcp_call(client, "save_calendar_entries",
                      {"items": [entry("Treino de ontem", 6, "19:00", "20:00", mobility="flexible", status="done")]})
    assert logged["ok"] is True


def test_claude_cannot_change_fixed_without_confirmation(client):
    e = client.post("/calendar", json=entry("Jiu-Jitsu", 8, "19:00", "20:30", category="training")).json()["data"]["entry"]
    attempt = mcp_call(client, "save_calendar_entries", {"items": [{"id": e["id"], "version": e["version"], "start": t(8, "18:00")}]})
    assert attempt["error"]["code"] == "CONFIRMATION_REQUIRED"
    confirmed = mcp_call(client, "save_calendar_entries", {"items": [
        {"id": e["id"], "version": e["version"], "start": t(8, "18:00"), "confirm_fixed": True,
         "reason": "Usuário pediu para antecipar"}]}, expect_ok=True)
    moved = confirmed["data"]["results"][0]["entry"]
    assert moved["start"] == "2026-10-08T18:00-03:00" and moved["end"] == "2026-10-08T19:30-03:00"  # duration kept
    # marking it done is not a protected change
    done = mcp_call(client, "save_calendar_entries", {"items": [{"id": e["id"], "version": moved["version"], "status": "done"}]})
    # (future entry marked done is allowed; it only changes status)
    assert done["ok"] is True
    # delete needs confirmation too
    d = mcp_call(client, "delete_entity", {"entity_type": "calendar_entry", "id": e["id"]})
    assert d["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_manual_edits_only_warn_on_overlap(client):
    client.post("/calendar", json=entry("A", 7, "14:00", "15:00"))
    r = client.post("/calendar", json=entry("B", 7, "14:30", "15:30"))
    assert r.status_code == 200
    assert r.json()["warnings"][0]["code"] == "OVERLAP"
    day = client.get("/schedule", params={"start": "2026-10-07", "end": "2026-10-07"}).json()["data"]["days"][0]
    assert all("overlaps_with" in e for e in day["entries"])


def test_swap_in_one_batch_is_allowed(client):
    a = mcp_call(client, "save_calendar_entries", {"items": [
        entry("A", 7, "14:00", "15:00", mobility="flexible"), entry("B", 7, "15:00", "16:00", mobility="flexible")]},
        expect_ok=True)["data"]["results"]
    ea, eb = a[0]["entry"], a[1]["entry"]
    swapped = mcp_call(client, "save_calendar_entries", {"items": [
        {"id": ea["id"], "version": ea["version"], "start": t(7, "15:00")},
        {"id": eb["id"], "version": eb["version"], "start": t(7, "14:00")}]})
    assert swapped["ok"] is True, swapped


def test_recurring_entries_exceptions_and_conflicts(client):
    # Jiu-Jitsu every Thursday 19:00 (Oct 8 is a Thursday)
    series = client.post("/calendar", json={**entry("Jiu-Jitsu", 8, "19:00", "20:30", category="training"),
                                            "rrule": "FREQ=WEEKLY;BYDAY=TH"}).json()["data"]["entry"]
    assert series["recurring"]
    sched = client.get("/schedule", params={"start": "2026-10-08", "end": "2026-10-22"}).json()["data"]["days"]
    thursdays = [d for d in sched if d["entries"]]
    assert [d["date"] for d in thursdays] == ["2026-10-08", "2026-10-15", "2026-10-22"]
    # Claude cannot put a block on top of an upcoming occurrence
    bad = mcp_call(client, "save_calendar_entries", {"items": [entry("Estudar", 15, "19:30", "20:00", mobility="flexible")]})
    assert bad["error"]["code"] == "CONFLICT_FIXED_EVENT"
    # mark just one occurrence as skipped
    res = client.patch(f"/calendar/{series['id']}", json={
        "scope": "this", "occurrence_start": t(15, "19:00"), "status": "skipped", "skip_reason": "viagem",
        "version": series["version"]}).json()["data"]["entry"]
    assert res["status"] == "skipped" and res["series_id"] == series["id"]
    ok = mcp_call(client, "save_calendar_entries", {"items": [entry("Estudar", 15, "19:30", "20:00", mobility="flexible")]})
    assert ok["ok"] is True  # skipped occurrences free the slot
    # cancelling an occurrence removes it from the schedule
    client.delete(f"/calendar/{series['id']}", params={"scope": "this", "occurrence_start": t(22, "19:00")})
    sched = client.get("/schedule", params={"start": "2026-10-22", "end": "2026-10-22"}).json()["data"]["days"][0]
    assert sched["entries"] == []
    # recurrence is evaluated in wall-clock time
    sched = client.get("/schedule", params={"start": "2026-11-05", "end": "2026-11-05"}).json()["data"]["days"][0]
    assert sched["entries"][0]["start"] == "2026-11-05T19:00-03:00"


def test_all_day_events_dont_block_time(client):
    client.post("/calendar", json={"title": "Feriado", "start": "2026-10-12T00:00", "end": "2026-10-13T00:00", "all_day": True})
    ok = mcp_call(client, "save_calendar_entries", {"items": [entry("Bloco", 12, "10:00", "11:00", mobility="flexible")]})
    assert ok["ok"] is True
    day = client.get("/schedule", params={"start": "2026-10-12", "end": "2026-10-12"}).json()["data"]["days"][0]
    assert day["all_day"][0]["title"] == "Feriado"


# ------------------------------------------------------------------ day plan
def test_set_day_plan_is_declarative_and_idempotent(client):
    fixed = client.post("/calendar", json=entry("Reunião", 8, "10:00", "11:00", category="meeting")).json()["data"]["entry"]
    task = client.post("/tasks", json={"title": "Faelo: revisar orchestrator"}).json()["data"]["task"]
    plan = {"plans": [{"date": "2026-10-08", "summary": "Dia de foco no Faelo",
                       "rationale": "Estudo cedo, reunião às 10h, trabalho à tarde.",
                       "blocks": [
                           {"title": "Estudo Python", "start": t(8, "08:00"), "end": t(8, "09:30"), "category": "study"},
                           {"title": "Faelo", "start": t(8, "13:00"), "end": t(8, "17:00"), "category": "work",
                            "task_id": task["id"]}]}]}
    dry = mcp_call(client, "set_day_plan", {**plan, "dry_run": True}, expect_ok=True)
    assert dry["meta"]["dry_run"] is True
    assert dry["data"]["plans"][0]["created"][0]["id"] == "(new)"
    assert client.get("/schedule", params={"start": "2026-10-08", "end": "2026-10-08"}).json()["data"]["days"][0]["plan"] is None
    first = mcp_call(client, "set_day_plan", plan, expect_ok=True)["data"]["plans"][0]
    assert len(first["created"]) == 2 and first["removed"] == []
    assert first["plan"]["rationale"].startswith("Estudo cedo")
    titles = [e["title"] for e in first["day"]["entries"]]
    assert titles == ["Estudo Python", "Reunião", "Faelo"]
    # same input again changes nothing
    second = mcp_call(client, "set_day_plan", plan, expect_ok=True)["data"]["plans"][0]
    assert second["created"] == [] and second["updated"] == [] and second["unchanged"] == 2
    # a new plan moves one block and removes the other; the fixed meeting is untouched
    plan2 = {"plans": [{"date": "2026-10-08", "blocks": [
        {"title": "Faelo", "start": t(8, "14:00"), "end": t(8, "17:00"), "category": "work", "task_id": task["id"]}]}]}
    third = mcp_call(client, "set_day_plan", plan2, expect_ok=True)["data"]["plans"][0]
    assert [e["title"] for e in third["updated"]] == ["Faelo"] and [r["title"] for r in third["removed"]] == ["Estudo Python"]
    assert any(e["title"] == "Reunião" for e in third["day"]["entries"])
    # task shows its scheduled block
    tk = client.get("/tasks", params={"ids": task["id"]}).json()["data"]["tasks"][0]
    assert tk["scheduled"][0]["start"] == "2026-10-08T14:00-03:00"
    # conflicts with the fixed meeting are rejected atomically
    bad = mcp_call(client, "set_day_plan", {"plans": [{"date": "2026-10-08", "blocks": [
        {"title": "Ruim", "start": t(8, "10:30"), "end": t(8, "11:30")}]}]})
    assert bad["error"]["code"] == "CONFLICT_FIXED_EVENT"
    same = client.get("/schedule", params={"start": "2026-10-08", "end": "2026-10-08"}).json()["data"]["days"][0]
    assert [e["title"] for e in same["entries"]] == ["Reunião", "Faelo"]
    assert fixed["id"] in [e["id"] for e in same["entries"]]


def test_completing_task_warns_about_future_blocks(client):
    task = client.post("/tasks", json={"title": "Relatório"}).json()["data"]["task"]
    mcp_call(client, "set_day_plan", {"plans": [{"date": "2026-10-09", "blocks": [
        {"title": "Relatório", "start": t(9, "14:00"), "end": t(9, "15:00"), "task_id": task["id"]}]}]}, expect_ok=True)
    env = mcp_call(client, "save_tasks", {"items": [{"id": task["id"], "version": task["version"], "status": "done"}]}, expect_ok=True)
    assert env["warnings"][0]["code"] == "TASK_HAS_FUTURE_BLOCKS"


# ------------------------------------------------------------------ study
ROADMAP = [{
    "name": "Tecnologia", "kind": "area", "client_ref": "tech", "children": [
        {"name": "Python", "client_ref": "py", "children": [
            {"name": "Básico", "client_ref": "py.basic", "difficulty": 1, "estimated_minutes": 600},
            {"name": "Async / Await", "client_ref": "py.async", "prerequisites": ["py.basic"], "difficulty": 4},
            {"name": "Typing", "client_ref": "py.typing", "prerequisites": ["py.basic"]}]},
        {"name": "FastAPI", "client_ref": "fastapi", "ref": "fa", "prerequisites": ["py.async"]}]}]


def test_study_import_rollups_and_availability(client):
    env = mcp_call(client, "save_study_topics", {"items": ROADMAP}, expect_ok=True)
    assert env["data"]["count"] == 6 and env["data"]["overview"]["topics"] == 4
    # re-import is idempotent
    again = mcp_call(client, "save_study_topics", {"items": ROADMAP}, expect_ok=True)
    assert {r["action"] for r in again["data"]["results"]} == {"unchanged"}
    av = mcp_call(client, "get_study", {"only_available": True}, expect_ok=True)["data"]["available"]
    assert [a["path"] for a in av] == ["Tecnologia › Python › Básico"]  # others are blocked by prerequisites
    basic = av[0]
    log = mcp_call(client, "log_study", {"topic_id": basic["id"], "minutes": 90, "progress": 100}, expect_ok=True)
    assert log["data"]["topic"]["status"] == "done" and log["data"]["topic"]["progress"] == 100
    av2 = mcp_call(client, "get_study", {"only_available": True})["data"]["available"]
    assert {a["path"].split(" › ")[-1] for a in av2} == {"Async / Await", "Typing"}
    tree = mcp_call(client, "get_study", {"depth": 3})["data"]
    root = tree["roots"][0]
    assert root["status"] == "in_progress" and root["leaves"] == "1/4" and root["progress"] == 25
    py = root["children"][0]
    assert py["leaves"] == "1/3" and py["minutes_spent"] == 90


def test_study_prerequisite_cycles_and_parent_cycles(client):
    mcp_call(client, "save_study_topics", {"items": ROADMAP}, expect_ok=True)
    async_t = client.get("/study", params={"depth": 5}).json()["data"]["roots"][0]["children"][0]["children"][1]
    bad = mcp_call(client, "save_study_topics", {"items": [{"id": async_t["id"], "version": async_t["version"],
                                                              "prerequisites": ["fastapi"]}]})
    assert bad["error"]["code"] == "VALIDATION" and "cycle" in bad["error"]["message"].lower()
    root = client.get("/study", params={"depth": 0}).json()["data"]["roots"][0]
    cyc = mcp_call(client, "save_study_topics", {"items": [{"id": root["id"], "version": root["version"],
                                                              "parent_id": async_t["id"]}]})
    assert cyc["error"]["code"] == "VALIDATION"


def test_finishing_a_study_block_logs_a_session(client):
    mcp_call(client, "save_study_topics", {"items": ROADMAP}, expect_ok=True)
    basic = mcp_call(client, "get_study", {"only_available": True})["data"]["available"][0]
    blk = mcp_call(client, "set_day_plan", {"plans": [{"date": "2026-10-07", "blocks": [
        {"title": "Estudar Python", "start": t(7, "14:00"), "end": t(7, "15:30"), "category": "study",
         "study_topic_id": basic["id"]}]}]}, expect_ok=True)["data"]["plans"][0]["created"][0]
    r = client.patch(f"/calendar/{blk['id']}", json={"status": "done", "version": blk["version"]})
    assert r.status_code == 200
    detail = client.get("/study", params={"topic_id": basic["id"]}).json()["data"]["topic"]
    assert detail["minutes_spent"] == 90 and detail["status"] == "in_progress"
    assert detail["recent_sessions"][0]["minutes"] == 90


# ------------------------------------------------------------------ routines / prefs
def test_routines_weekly_quota_and_preferences(client):
    r = client.post("/routines", json={"name": "Jiu-Jitsu", "target_per_week": 3, "duration_minutes": 90,
                                       "preferred_days": [1, 3, 5], "preferred_start": "19:00"}).json()["data"]["routine"]
    client.post("/calendar", json={**entry("Jiu-Jitsu", 6, "19:00", "20:30", status="done"), "routine_id": r["id"], "mobility": "flexible"})
    ctx = mcp_call(client, "get_context", expect_ok=True)["data"]
    jj = ctx["routines"][0]
    assert jj["target_per_week"] == 3 and jj["done_this_week"] == 1 and jj["planned_this_week"] == 0
    p = mcp_call(client, "save_preferences", {"patch": {"wake_time": "06:00", "planning_rules": ["Sem estudo após 22h"]}}, expect_ok=True)
    assert p["data"]["preferences"]["wake_time"] == "06:00"
    ctx = mcp_call(client, "get_context")["data"]
    assert ctx["preferences"]["planning_rules"] == ["Sem estudo após 22h"]
    bad = mcp_call(client, "save_preferences", {"patch": {"wake_time": "25:00"}})
    assert bad["ok"] is False


# ------------------------------------------------------------------ audit / undo
def test_undo_batch_reverts_and_is_guarded(client):
    task = client.post("/tasks", json={"title": "Original"}).json()["data"]["task"]
    env = mcp_call(client, "save_tasks", {"items": [{"id": task["id"], "version": task["version"], "title": "Alterado pela IA"},
                                                    {"title": "Nova tarefa da IA"}]}, expect_ok=True)
    batch = env["meta"]["batch_id"]
    assert client.get("/tasks").json()["data"]["count"] == 2
    undone = mcp_call(client, "undo_operation", {"batch_id": batch}, expect_ok=True)
    assert {r["was"] for r in undone["data"]["reverted"]} == {"create", "update"}
    tasks = client.get("/tasks").json()["data"]["tasks"]
    assert [x["title"] for x in tasks] == ["Original"]
    twice = mcp_call(client, "undo_operation", {"batch_id": batch})
    assert twice["error"]["code"] == "UNDO_NOT_POSSIBLE"
    # a change made after the batch blocks the undo
    env2 = mcp_call(client, "save_tasks", {"items": [{"id": task["id"], "version": tasks[0]["version"], "title": "Passo 2"}]}, expect_ok=True)
    cur = client.get("/tasks").json()["data"]["tasks"][0]
    client.patch(f"/tasks/{cur['id']}", json={"title": "Usuário mexeu", "version": cur["version"]})
    blocked = mcp_call(client, "undo_operation", {"batch_id": env2["meta"]["batch_id"]})
    assert blocked["error"]["code"] == "UNDO_NOT_POSSIBLE"


def test_delete_is_soft_cascades_and_undoable(client):
    p = client.post("/projects", json={"name": "Faelo"}).json()["data"]["project"]
    tk = client.post("/tasks", json={"title": "T", "project_id": p["id"]}).json()["data"]["task"]
    env = mcp_call(client, "delete_entity", {"entity_type": "project", "id": p["id"]}, expect_ok=True)
    assert env["data"]["detached_tasks"] == 1
    assert client.get("/projects").json()["data"]["projects"] == []
    assert client.get("/tasks").json()["data"]["tasks"][0].get("project_id") is None
    mcp_call(client, "undo_operation", {"batch_id": env["meta"]["batch_id"]}, expect_ok=True)
    assert client.get("/projects").json()["data"]["projects"][0]["name"] == "Faelo"
    assert client.get("/tasks").json()["data"]["tasks"][0]["project_id"] == p["id"]
    assert tk["id"]


def test_rejected_operations_are_logged(client):
    mcp_call(client, "save_calendar_entries", {"items": [entry("Ontem", 6, "10:00", "11:00", mobility="flexible")]})
    log = mcp_call(client, "get_operation_log", {}, expect_ok=True)["data"]["batches"]
    assert log[0]["result"] == "rejected" and log[0]["changes"][0]["error"] == "PAST_DATE"


def test_context_reports_manual_changes_to_claude(client):
    client.post("/tasks", json={"title": "Criada na UI"})
    ctx = mcp_call(client, "get_context", expect_ok=True)["data"]
    assert ctx["recent_manual_changes"][0]["summary"] == "Criada na UI"
    assert ctx["tasks"]["open"] == 1


def test_edit_all_occurrences_keeps_series_anchor(client):
    series = client.post("/calendar", json={**entry("Aula", 8, "19:00", "20:00", category="training"),
                                            "rrule": "FREQ=WEEKLY;BYDAY=TH"}).json()["data"]["entry"]
    # from the 15th's point of view, move to 18:00-19:00 for the whole series
    r = client.patch(f"/calendar/{series['id']}", json={
        "version": series["version"], "scope": "all", "occurrence_start": t(15, "19:00"),
        "start": t(15, "18:00"), "end": t(15, "19:00")})
    assert r.status_code == 200, r.text
    days = client.get("/schedule", params={"start": "2026-10-08", "end": "2026-10-15"}).json()["data"]["days"]
    assert [(d["date"], d["entries"][0]["start"][11:16]) for d in days if d["entries"]] == [
        ("2026-10-08", "18:00"), ("2026-10-15", "18:00")]


# ------------------------------------------------------------------ workouts
GYM = {"name": "Academia", "target_per_week": 3, "duration_minutes": 60, "workouts": [
    {"name": "Treino A · Peito e tríceps", "exercises": [
        {"name": "Supino reto", "sets": 4, "reps": "8-10", "load": "60kg", "rest_seconds": 90},
        {"name": "Crucifixo", "sets": 3, "reps": "12"},
        {"name": "Tríceps corda", "sets": 3, "reps": "12", "load": "25kg"}]},
    {"name": "Treino B · Costas", "exercises": [{"name": "Remada curvada", "sets": 4, "reps": "10"}]},
]}


def test_workout_plan_is_customizable_and_keys_are_stable(client):
    r = mcp_call(client, "save_routines", {"items": [GYM]}, expect_ok=True)["data"]["results"][0]["routine"]
    a, b = r["workouts"]
    assert a["key"] and b["key"] and a["exercises"][0]["key"] and a["exercises"][0]["rest_seconds"] == 90
    # edit: rename one exercise keeping keys, add another -> keys preserved
    a["exercises"][0]["name"] = "Supino inclinado"
    a["exercises"].append({"name": "Flexão", "reps": "até a falha"})
    r2 = mcp_call(client, "save_routines", {"items": [{"id": r["id"], "version": r["version"], "workouts": [a, b]}]},
                  expect_ok=True)["data"]["results"][0]["routine"]
    assert r2["workouts"][0]["exercises"][0]["key"] == a["exercises"][0]["key"]
    assert [e["name"] for e in r2["workouts"][0]["exercises"]][-1] == "Flexão"
    dup = mcp_call(client, "save_routines", {"items": [{"id": r["id"], "version": r2["version"], "workouts": [
        {"key": "x", "name": "A"}, {"key": "x", "name": "B"}]}]})
    assert dup["error"]["code"] == "VALIDATION"
    ctx = mcp_call(client, "get_context", expect_ok=True)["data"]
    assert ctx["routines"][0]["workouts"][0]["exercises"] == 4  # slim in the bootstrap context
    full = mcp_call(client, "get_routines", {"routine_id": r["id"]}, expect_ok=True)["data"]["routines"][0]
    assert full["workouts"][0]["exercises"][1]["name"] == "Crucifixo"


def test_log_workout_done_and_not_done_flow(client):
    r = client.post("/routines", json=GYM).json()["data"]["routine"]
    wa = r["workouts"][0]
    session = {"routine_id": r["id"]}
    # several workouts: must choose one
    bad = mcp_call(client, "log_workout", {"item": session})
    assert bad["error"]["code"] == "VALIDATION" and wa["key"] in bad["error"]["message"]
    entry = client.post("/calendar", json={**entry_payload("Academia", 7, "18:00", "19:00"), "routine_id": r["id"], "mobility": "flexible", "category": "training"}).json()["data"]["entry"]
    s = mcp_call(client, "log_workout", {"item": {"workout_key": wa["key"], "entry_id": entry["id"]}}, expect_ok=True)["data"]["session"]
    assert s["summary"] == {"total": 3, "done": 0, "not_done": 0, "pending": 3} and s["workout_name"].startswith("Treino A")
    ex = s["exercises"]
    # same entry again resumes the same session
    again = mcp_call(client, "log_workout", {"item": {"entry_id": entry["id"]}}, expect_ok=True)["data"]["session"]
    assert again["id"] == s["id"]
    # mark one done (with what was actually done), one not done, add an extra exercise
    upd = mcp_call(client, "log_workout", {"item": {"id": s["id"], "version": s["version"], "exercises": [
        {"key": ex[0]["key"], "done": True, "actual": "4x8 @ 62kg"},
        {"key": ex[1]["key"], "done": False, "note": "ombro doendo"},
        {"name": "Abdominal", "done": True}]}}, expect_ok=True)["data"]["session"]
    assert upd["summary"] == {"total": 4, "done": 2, "not_done": 1, "pending": 1}
    assert upd["exercises"][0]["actual"] == "4x8 @ 62kg" and upd["exercises"][3].get("extra") is True
    # editing the plan afterwards does not rewrite history
    client.patch(f"/routines/{r['id']}", json={"version": r["version"], "workouts": [{"key": wa["key"], "name": "Novo A", "exercises": []}, r["workouts"][1]]})
    snap = client.get(f"/workouts/{s['id']}").json()["data"]["session"]
    assert snap["exercises"][0]["name"] == "Supino reto"
    # finish: pending -> not done, entry marked done, duration from the entry
    fin = mcp_call(client, "log_workout", {"item": {"id": s["id"], "version": upd["version"], "finished": True, "effort": 8}}, expect_ok=True)["data"]
    assert fin["session"]["finished"] and fin["session"]["summary"] == {"total": 4, "done": 2, "not_done": 2, "pending": 0}
    assert fin["session"]["duration_minutes"] == 60 and fin["entry_status"] == "done"
    # history shows up for Claude
    hist = mcp_call(client, "get_routines", {"routine_id": r["id"], "recent_sessions": 3}, expect_ok=True)["data"]["routines"][0]
    assert hist["recent_sessions"][0]["summary"]["done"] == 2 and hist["done_this_week"] == 1
    # undo the finishing batch
    mcp_call(client, "undo_operation", {"batch_id": fin and mcp_call(client, "get_operation_log", {}, expect_ok=True)["data"]["batches"][0]["batch_id"]})


def entry_payload(title, day, s, e):
    return {"title": title, "start": f"2026-10-{day:02d}T{s}:00", "end": f"2026-10-{day:02d}T{e}:00"}


def test_log_workout_from_a_recurring_occurrence_and_cascade(client):
    r = client.post("/routines", json={"name": "Jiu-Jitsu", "workouts": [{"name": "Aula", "exercises": [
        {"name": "Aquecimento"}, {"name": "Drill de passagem"}, {"name": "Rola"}]}]}).json()["data"]["routine"]
    series = client.post("/calendar", json={**entry_payload("Jiu-Jitsu", 8, "19:00", "20:30"), "rrule": "FREQ=WEEKLY;BYDAY=TH",
                                            "routine_id": r["id"], "category": "training"}).json()["data"]["entry"]
    needs_occ = mcp_call(client, "log_workout", {"item": {"entry_id": series["id"]}})
    assert needs_occ["error"]["code"] == "VALIDATION" and "occurrence_start" in needs_occ["error"]["message"]
    s = mcp_call(client, "log_workout", {"item": {"entry_id": series["id"], "occurrence_start": "2026-10-08T19:00:00",
                                                   "exercises": [{"name": "Aquecimento", "done": True}, {"name": "Rola", "done": False}],
                                                   "finished": True, "notes": "Foco em passagem de guarda"}}, expect_ok=True)["data"]
    assert s["entry_status"] == "done" and s["session"]["summary"]["not_done"] == 2
    day = client.get("/schedule", params={"start": "2026-10-08", "end": "2026-10-08"}).json()["data"]["days"][0]
    assert day["entries"][0]["status"] == "done" and day["entries"][0]["series_id"] == series["id"]
    nxt = client.get("/schedule", params={"start": "2026-10-15", "end": "2026-10-15"}).json()["data"]["days"][0]
    assert nxt["entries"][0]["status"] == "planned"
    d = mcp_call(client, "delete_entity", {"entity_type": "routine", "id": r["id"]}, expect_ok=True)
    assert d["data"]["deleted_sessions"] == 1
    mcp_call(client, "undo_operation", {"batch_id": d["meta"]["batch_id"]}, expect_ok=True)
    assert client.get(f"/workouts/{s['session']['id']}").status_code == 200


def test_undo_restores_moved_block_times(client):
    e = mcp_call(client, "save_calendar_entries", {"items": [entry("Estudo", 8, "09:00", "10:00", mobility="flexible")]},
                 expect_ok=True)["data"]["results"][0]["entry"]
    moved = mcp_call(client, "save_calendar_entries", {"items": [{"id": e["id"], "version": e["version"], "start": t(8, "14:00")}]},
                     expect_ok=True)
    assert moved["data"]["results"][0]["entry"]["start"] == "2026-10-08T14:00-03:00"
    mcp_call(client, "undo_operation", {"batch_id": moved["meta"]["batch_id"]}, expect_ok=True)
    day = client.get("/schedule", params={"start": "2026-10-08", "end": "2026-10-08"}).json()["data"]["days"][0]
    assert day["entries"][0]["start"] == "2026-10-08T09:00-03:00" and day["entries"][0]["end"] == "2026-10-08T10:00-03:00"
