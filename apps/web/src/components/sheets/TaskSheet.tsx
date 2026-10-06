"use client";

import { Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAct, useProjects } from "@/lib/hooks";
import { dur, fmtShort, hm, ymd } from "@/lib/time";
import type { Priority, Task, TaskStatus } from "@/lib/types";
import { Button, ClaudeBadge, Field, Segmented, Sheet, inputCls } from "../ui";

export type TaskDefaults = Partial<{
  title: string; status: TaskStatus; do_date: string; due_date: string; project_id: string; priority: Priority;
}>;

const STATUS_OPTS: { value: TaskStatus; label: string }[] = [
  { value: "inbox", label: "Inbox" },
  { value: "todo", label: "A fazer" },
  { value: "doing", label: "Fazendo" },
  { value: "done", label: "Feita" },
];
const PRIORITIES: { value: Priority; label: string }[] = [
  { value: "low", label: "Baixa" },
  { value: "medium", label: "Média" },
  { value: "high", label: "Alta" },
  { value: "urgent", label: "Urgente" },
];

export function TaskSheet({ task, defaults, onClose }: { task: Task | null; defaults?: TaskDefaults; onClose: () => void }) {
  const act = useAct();
  const projects = useProjects();
  const [f, setF] = useState(() => ({
    title: task?.title ?? defaults?.title ?? "",
    description: task?.description ?? "",
    status: (task?.status ?? defaults?.status ?? "todo") as TaskStatus,
    priority: (task?.priority ?? defaults?.priority ?? "medium") as Priority,
    due_date: task?.due_date ?? defaults?.due_date ?? "",
    do_date: task?.do_date ?? defaults?.do_date ?? "",
    estimated_minutes: task?.estimated_minutes ? String(task.estimated_minutes) : "",
    project_id: task?.project_id ?? defaults?.project_id ?? "",
    category: task?.category ?? "",
    notes: task?.notes ?? "",
  }));
  const [confirmDel, setConfirmDel] = useState(false);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));

  const save = async () => {
    const body = {
      title: f.title.trim(),
      description: f.description || null,
      status: f.status,
      priority: f.priority,
      due_date: f.due_date || null,
      do_date: f.do_date || null,
      estimated_minutes: f.estimated_minutes ? Number(f.estimated_minutes) : null,
      project_id: f.project_id || null,
      category: f.category || null,
      notes: f.notes || null,
    };
    const r = await act(
      () => (task ? api.patch(`/tasks/${task.id}`, { ...body, version: task.version }) : api.post("/tasks", body)),
      task ? "Tarefa atualizada" : "Tarefa criada",
    );
    if (r) onClose();
  };

  const remove = async () => {
    if (!task) return;
    const r = await act(() => api.del(`/tasks/${task.id}`), "Tarefa excluída");
    if (r) onClose();
  };

  return (
    <Sheet
      open
      onClose={onClose}
      title={task ? "Editar tarefa" : "Nova tarefa"}
      footer={
        <div className="flex items-center gap-2">
          {task && (
            <Button variant="danger" onClick={confirmDel ? remove : () => setConfirmDel(true)} aria-label="Excluir">
              <Trash2 className="size-4" /> {confirmDel ? "Confirmar" : ""}
            </Button>
          )}
          <Button className="flex-1" onClick={save} disabled={!f.title.trim()}>
            {task ? "Salvar" : "Criar tarefa"}
          </Button>
        </div>
      }
    >
      <div className="space-y-4 pt-1">
        <input
          autoFocus={!task}
          className="w-full bg-transparent text-xl font-semibold tracking-tight outline-none placeholder:text-faint"
          placeholder="O que precisa ser feito?"
          value={f.title}
          onChange={(e) => set("title", e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && f.title.trim() && save()}
        />
        {task && (
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            {task.created_by === "claude" && (
              <span className="inline-flex items-center gap-1">
                <ClaudeBadge /> criada pelo Claude
              </span>
            )}
            {task.scheduled?.map((s) => (
              <span key={s.id} className="rounded-full bg-surface2 px-2 py-0.5">
                📅 {fmtShort(ymd(s.start))} {hm(s.start)}–{hm(s.end)}
              </span>
            ))}
          </div>
        )}
        <Segmented value={f.status} onChange={(v) => set("status", v)} options={STATUS_OPTS} />
        <Field label="Descrição">
          <textarea className={inputCls} rows={3} value={f.description} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Fazer em" hint="O dia em que pretende fazer">
            <input type="date" className={inputCls} value={f.do_date} onChange={(e) => set("do_date", e.target.value)} />
          </Field>
          <Field label="Prazo" hint="Data limite">
            <input type="date" className={inputCls} value={f.due_date} onChange={(e) => set("due_date", e.target.value)} />
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Projeto">
            <select className={inputCls} value={f.project_id} onChange={(e) => set("project_id", e.target.value)}>
              <option value="">Sem projeto</option>
              {projects.data?.projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Duração estimada (min)">
            <input
              type="number" inputMode="numeric" min={1} max={1440} className={inputCls} placeholder="ex.: 45"
              value={f.estimated_minutes} onChange={(e) => set("estimated_minutes", e.target.value)}
            />
          </Field>
        </div>
        {f.estimated_minutes && <p className="-mt-2 text-xs text-faint">≈ {dur(Number(f.estimated_minutes))}</p>}
        <Field label="Prioridade">
          <Segmented value={f.priority} onChange={(v) => set("priority", v)} options={PRIORITIES} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Categoria">
            <input className={inputCls} value={f.category} onChange={(e) => set("category", e.target.value)} placeholder="ex.: backend" />
          </Field>
        </div>
        <Field label="Notas">
          <textarea className={inputCls} rows={2} value={f.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>
      </div>
    </Sheet>
  );
}
