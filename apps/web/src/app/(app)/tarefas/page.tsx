"use client";

import { Inbox, Search } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { TaskRow } from "@/components/items";
import { useSheets } from "@/components/sheets/host";
import { Empty, SectionTitle, Segmented, Spinner, inputCls } from "@/components/ui";
import { toggleTask } from "@/lib/actions";
import { api } from "@/lib/api";
import { useAct, useContextQ, useProjects, useTasks } from "@/lib/hooks";
import { addDays, relDay } from "@/lib/time";
import type { Task } from "@/lib/types";

type Tab = "inbox" | "today" | "upcoming" | "all" | "done";
const TABS: { value: Tab; label: string }[] = [
  { value: "inbox", label: "Inbox" },
  { value: "today", label: "Hoje" },
  { value: "upcoming", label: "Próximas" },
  { value: "all", label: "Todas" },
  { value: "done", label: "Feitas" },
];

function group(tasks: Task[], by: "project" | "date", today: string): [string, Task[]][] {
  const m = new Map<string, Task[]>();
  for (const t of tasks) {
    const key = by === "project" ? t.project_name ?? "Sem projeto" : t.do_date ? relDay(t.do_date, today) : t.due_date ? `Prazo ${relDay(t.due_date, today).toLowerCase()}` : "Sem data";
    m.set(key, [...(m.get(key) ?? []), t]);
  }
  return [...m.entries()];
}

function TasksInner() {
  const sheets = useSheets();
  const act = useAct();
  const ctx = useContextQ();
  const today = ctx.data?.today ?? new Date().toISOString().slice(0, 10);
  const params = useSearchParams();
  const [tab, setTab] = useState<Tab>((params.get("tab") as Tab) || "today");
  const [q, setQ] = useState("");
  const [project, setProject] = useState("");
  const [quick, setQuick] = useState("");
  const projects = useProjects();

  const query = useMemo(() => {
    const base: Record<string, unknown> = { limit: 300, q: q || undefined, project_id: project || undefined };
    if (tab === "inbox") return { ...base, status: ["inbox"] };
    if (tab === "done") return { ...base, status: ["done"] };
    if (tab === "today") return { ...base, include_done_since: today };
    return base;
  }, [tab, q, project, today]);
  const tasksQ = useTasks(query);
  const all = useMemo(() => tasksQ.data?.tasks ?? [], [tasksQ.data]);

  const shown = useMemo(() => {
    if (tab === "today")
      return all.filter((t) => (t.status === "done" ? t.completed_at?.slice(0, 10) === today : t.overdue || (t.do_date && t.do_date <= today) || t.due_date === today));
    if (tab === "upcoming") return all.filter((t) => !(t.overdue || (t.do_date && t.do_date <= today) || t.due_date === today) && (t.do_date || t.due_date));
    if (tab === "done") return [...all].sort((a, b) => (b.completed_at ?? "").localeCompare(a.completed_at ?? ""));
    return all;
  }, [all, tab, today]);

  const groups = useMemo(() => {
    if (tab === "today") {
      const o = shown.filter((t) => t.overdue && t.status !== "done");
      const d = shown.filter((t) => !t.overdue && t.status !== "done");
      const f = shown.filter((t) => t.status === "done");
      return ([["Atrasadas", o], ["Para hoje", d], ["Feitas hoje", f]] as [string, Task[]][]).filter(([, l]) => l.length);
    }
    if (tab === "upcoming") return group([...shown].sort((a, b) => (a.do_date ?? a.due_date ?? "").localeCompare(b.do_date ?? b.due_date ?? "")), "date", today);
    if (tab === "all") return group(shown, "project", today);
    return shown.length ? ([["", shown]] as [string, Task[]][]) : [];
  }, [shown, tab, today]);

  const add = async (e: React.FormEvent) => {
    e.preventDefault();
    const title = quick.trim();
    if (!title) return;
    const body: Record<string, unknown> = { title, status: tab === "inbox" ? "inbox" : "todo" };
    if (tab === "today") body.do_date = today;
    if (project) body.project_id = project;
    const r = await act(() => api.post("/tasks", body));
    if (r) setQuick("");
  };

  const emptyText: Record<Tab, [string, string]> = {
    inbox: ["Inbox vazio", "Capture ideias rápidas aqui. O Claude pode fazer a triagem depois."],
    today: ["Nada para hoje", "Adicione uma tarefa ou peça ao Claude para planejar seu dia."],
    upcoming: ["Nada agendado", "Tarefas com data aparecem aqui."],
    all: ["Nenhuma tarefa", "Crie a primeira acima."],
    done: ["Nada concluído ainda", ""],
  };

  return (
    <div>
      <header className="pb-3 pt-2">
        <h1 className="text-[28px] font-semibold tracking-tight">Tarefas</h1>
      </header>
      <div className="scroll-hide -mx-4 overflow-x-auto px-4 lg:mx-0 lg:px-0">
        <div className="min-w-[340px]"><Segmented value={tab} onChange={setTab} options={TABS} /></div>
      </div>

      <form onSubmit={add} className="mt-3">
        <input
          className={inputCls}
          placeholder={tab === "inbox" ? "Capturar no inbox…" : "Nova tarefa…  (Enter para adicionar)"}
          value={quick}
          onChange={(e) => setQuick(e.target.value)}
        />
      </form>

      <div className="mt-3 flex gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" />
          <input className={`${inputCls} pl-9`} placeholder="Buscar" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <select className={`${inputCls} max-w-[44%]`} value={project} onChange={(e) => setProject(e.target.value)} aria-label="Filtrar por projeto">
          <option value="">Todos os projetos</option>
          {projects.data?.projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>

      {tasksQ.isLoading ? (
        <div className="grid place-items-center py-16"><Spinner /></div>
      ) : groups.length === 0 ? (
        <Empty icon={<Inbox className="size-5" />} title={emptyText[tab][0]} hint={emptyText[tab][1]} />
      ) : (
        groups.map(([title, list]) => (
          <section key={title}>
            {title && <SectionTitle right={<span className="text-xs text-faint">{list.length}</span>}>{title}</SectionTitle>}
            <div className="-mx-1">
              {list.map((t) => (
                <TaskRow
                  key={t.id} task={t} today={today} showProject={tab !== "all"}
                  onOpen={() => sheets.task(t)} onToggle={() => act(() => toggleTask(t))}
                />
              ))}
            </div>
          </section>
        ))
      )}
      <p className="sr-only">{addDays(today, 0)}</p>
    </div>
  );
}

export default function TasksPage() {
  return (
    <Suspense fallback={<div className="grid place-items-center py-24"><Spinner /></div>}>
      <TasksInner />
    </Suspense>
  );
}
