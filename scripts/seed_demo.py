"""Seeds demo data through the real HTTP API + MCP endpoint (dev only).

    python scripts/seed_demo.py http://localhost:8000 you@email.com yourpassword
"""
import json
import sys
from datetime import date, timedelta

import httpx

base, email, password = sys.argv[1:4]
c = httpx.Client(base_url=base, timeout=30)
token = c.post("/auth/login", json={"email": email, "password": password}).json()["data"]["token"]
H = {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"}
_id = 0


def tool(name: str, args: dict) -> dict:
    global _id
    _id += 1
    r = c.post("/mcp", headers=H, json={"jsonrpc": "2.0", "id": _id, "method": "tools/call",
                                         "params": {"name": name, "arguments": args}})
    text = r.json()["result"]["content"][0]["text"]
    try:
        env = json.loads(text)
    except ValueError:
        raise SystemExit(f"{name}: {text}")
    if not env["ok"]:
        raise SystemExit(f"{name}: {env['error']}")
    return env["data"]


today = date.today()
tomorrow = today + timedelta(days=1)
d = lambda x: x.isoformat()  # noqa: E731

proj = tool("save_projects", {"items": [
    {"name": "Faelo", "area": "work", "client_ref": "p.faelo",
     "description": "Plataforma de agentes. Prioridade: estabilidade do orchestrator e webhooks."},
    {"name": "Estudos de backend", "area": "study", "client_ref": "p.study"},
]})["results"]
faelo = proj[0]["project"]["id"]

tasks = tool("save_tasks", {"items": [
    {"title": "Revisar orchestrator", "project_id": faelo, "priority": "high", "do_date": d(today), "estimated_minutes": 120, "client_ref": "t1"},
    {"title": "Corrigir webhook", "project_id": faelo, "priority": "urgent", "due_date": d(today + timedelta(days=2)), "estimated_minutes": 60, "client_ref": "t2"},
    {"title": "Implementar feature de filas", "project_id": faelo, "due_date": d(today + timedelta(days=6)), "client_ref": "t3"},
    {"title": "Comprar presente da Mari", "status": "inbox", "client_ref": "t4"},
    {"title": "Pagar boleto do condomínio", "due_date": d(today - timedelta(days=1)), "priority": "high", "client_ref": "t5"},
]})["results"]
t_orch = tasks[0]["task"]["id"]

routines = tool("save_routines", {"items": [
    {"name": "Jiu-Jitsu", "target_per_week": 3, "duration_minutes": 90, "preferred_days": [1, 3, 5], "preferred_start": "19:00",
     "notes": "Aula na academia, levar kimono.", "client_ref": "r.bjj",
     "workouts": [{"name": "Aula", "exercises": [
         {"name": "Aquecimento e mobilidade", "notes": "10 min"},
         {"name": "Técnica do dia"},
         {"name": "Drill de passagem de guarda", "reps": "5 min por lado"},
         {"name": "Rola", "reps": "5 rounds de 5 min"}]}]},
    {"name": "Academia", "target_per_week": 3, "duration_minutes": 60, "preferred_days": [0, 2, 4], "preferred_start": "07:00",
     "client_ref": "r.gym",
     "workouts": [
         {"name": "Treino A · Peito e tríceps", "exercises": [
             {"name": "Supino reto", "sets": 4, "reps": "8-10", "load": "60kg", "rest_seconds": 90},
             {"name": "Supino inclinado com halteres", "sets": 3, "reps": "10-12", "load": "22kg", "rest_seconds": 75},
             {"name": "Crucifixo na polia", "sets": 3, "reps": "12", "load": "15kg"},
             {"name": "Tríceps corda", "sets": 3, "reps": "12", "load": "25kg"},
             {"name": "Tríceps testa", "sets": 3, "reps": "10", "load": "20kg"}]},
         {"name": "Treino B · Costas e bíceps", "exercises": [
             {"name": "Barra fixa", "sets": 4, "reps": "6-8", "load": "peso do corpo"},
             {"name": "Remada curvada", "sets": 4, "reps": "10", "load": "50kg"},
             {"name": "Puxada alta", "sets": 3, "reps": "12", "load": "55kg"},
             {"name": "Rosca direta", "sets": 3, "reps": "10", "load": "30kg"}]},
         {"name": "Treino C · Pernas", "exercises": [
             {"name": "Agachamento livre", "sets": 4, "reps": "8", "load": "80kg", "rest_seconds": 120},
             {"name": "Leg press", "sets": 4, "reps": "12", "load": "180kg"},
             {"name": "Stiff", "sets": 3, "reps": "10", "load": "50kg"},
             {"name": "Panturrilha em pé", "sets": 4, "reps": "15"}]}]},
]})["results"]
bjj, gym = routines[0]["routine"]["id"], routines[1]["routine"]["id"]

tool("save_calendar_entries", {"items": [
    {"title": "Jiu-Jitsu", "start": f"{d(today)}T19:00", "end": f"{d(today)}T20:30", "category": "training",
     "rrule": "FREQ=WEEKLY;BYDAY=TU,TH", "mobility": "fixed", "routine_id": bjj, "client_ref": "e.bjj"},
    {"title": "Reunião de produto", "start": f"{d(tomorrow)}T10:00", "end": f"{d(tomorrow)}T11:00", "category": "meeting", "client_ref": "e.meet"},
]})

tool("save_study_topics", {"items": [{
    "name": "Tecnologia", "kind": "area", "client_ref": "tech", "children": [
        {"name": "Backend", "client_ref": "backend", "children": [
            {"name": "Python", "client_ref": "py", "children": [
                {"name": "Fundamentos", "client_ref": "py.basics", "difficulty": 1, "estimated_minutes": 600, "status": "done"},
                {"name": "Typing", "client_ref": "py.typing", "difficulty": 2, "estimated_minutes": 180, "prerequisites": ["py.basics"]},
                {"name": "Async / Await", "client_ref": "py.async", "difficulty": 4, "estimated_minutes": 300, "prerequisites": ["py.basics"], "progress": 30,
                 "resources": [{"title": "Real Python: Async IO", "url": "https://realpython.com/async-io-python/", "kind": "article"}]},
                {"name": "Performance", "client_ref": "py.perf", "difficulty": 4, "prerequisites": ["py.async"]},
            ]},
            {"name": "FastAPI", "client_ref": "fastapi", "prerequisites": ["py.async"], "children": [
                {"name": "Dependências e rotas", "client_ref": "fa.routes", "prerequisites": ["py.typing"]},
                {"name": "WebSockets", "client_ref": "fa.ws", "difficulty": 3},
            ]},
            {"name": "PostgreSQL", "client_ref": "pg", "children": [
                {"name": "Índices e planos de execução", "client_ref": "pg.idx", "difficulty": 3},
                {"name": "Transações e locks", "client_ref": "pg.tx", "difficulty": 4},
            ]},
            {"name": "Redis e filas", "client_ref": "redis"},
        ]},
    ]}]})

async_topic = next(a for a in tool("get_study", {"only_available": True})["available"] if "Async" in a["path"])
tool("set_day_plan", {"plans": [
    {"date": d(today), "summary": "Foco no Faelo, estudo cedo",
     "rationale": "Estudo de async logo cedo (mente fresca), trabalho no orchestrator à tarde em bloco longo, treino às 19h fixo.",
     "blocks": [
         {"title": "Estudar Async / Await", "start": f"{d(today)}T14:00", "end": f"{d(today)}T15:30", "category": "study", "study_topic_id": async_topic["id"]},
         {"title": "Faelo · revisar orchestrator", "start": f"{d(today)}T15:45", "end": f"{d(today)}T18:15", "category": "work", "task_id": t_orch},
     ]},
    {"date": d(tomorrow), "summary": "Reunião às 10h, resto do dia no Faelo",
     "rationale": "Antes da reunião: estudo curto. Depois: bloco de trabalho profundo.",
     "blocks": [
         {"title": "Academia · Treino A", "start": f"{d(tomorrow)}T07:00", "end": f"{d(tomorrow)}T08:00", "category": "training", "routine_id": gym},
         {"title": "Estudar Typing", "start": f"{d(tomorrow)}T08:15", "end": f"{d(tomorrow)}T09:45", "category": "study"},
         {"title": "Faelo · corrigir webhook", "start": f"{d(tomorrow)}T13:00", "end": f"{d(tomorrow)}T15:00", "category": "work"},
     ]},
]})
print("seeded")
