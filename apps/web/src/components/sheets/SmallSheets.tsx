"use client";

import { CheckSquare, Lock, Move, Trash2 } from "lucide-react";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAct, useContextQ, useTopic } from "@/lib/hooks";
import { WEEKDAYS } from "@/lib/time";
import type { Project, Routine, Workout } from "@/lib/types";
import { Button, Field, Segmented, Sheet, Toggle, cx, inputCls } from "../ui";
import { WorkoutPlanEditor } from "./WorkoutPlanEditor";

// ------------------------------------------------------------------ log study
export function LogStudySheet({ topicId, entryId, onClose }: { topicId: string; entryId?: string; onClose: () => void }) {
  const act = useAct();
  const ctx = useContextQ();
  const detail = useTopic(topicId);
  const topic = detail.data?.topic;
  const [minutes, setMinutes] = useState("45");
  const [notes, setNotes] = useState("");
  const [progress, setProgress] = useState<number | null>(null);
  const [date, setDate] = useState("");
  const leaf = !!topic && !topic.leaves;
  const p = progress ?? topic?.progress ?? 0;

  const save = async () => {
    const r = await act(
      () =>
        api.post("/study/log", {
          topic_id: topicId,
          minutes: Number(minutes),
          notes: notes || null,
          date: date ? `${date}T00:00:00` : null,
          progress: leaf && progress !== null ? progress : null,
          entry_id: entryId ?? null,
          mark_entry_done: !!entryId,
        }),
      "Estudo registrado",
    );
    if (r) onClose();
  };

  return (
    <Sheet open onClose={onClose} title="Registrar estudo" footer={<Button className="w-full" onClick={save} disabled={!Number(minutes)}>Registrar</Button>}>
      <div className="space-y-4 pt-1">
        <p className="text-sm text-muted">{topic?.path ?? "…"}</p>
        <Field label="Quanto tempo?">
          <div className="mb-2 flex gap-1.5">
            {[25, 45, 60, 90, 120].map((m) => (
              <button key={m} type="button" onClick={() => setMinutes(String(m))}
                className={cx("h-9 flex-1 rounded-lg text-sm font-medium", minutes === String(m) ? "bg-ink text-inkfg" : "bg-surface2 text-muted")}>
                {m}
              </button>
            ))}
          </div>
          <input type="number" inputMode="numeric" min={1} className={inputCls} value={minutes} onChange={(e) => setMinutes(e.target.value)} />
        </Field>
        {leaf && (
          <Field label={`Progresso do tópico · ${p}%`}>
            <input type="range" min={0} max={100} step={5} value={p} onChange={(e) => setProgress(Number(e.target.value))} className="w-full accent-[var(--ink)]" />
            <button type="button" className="mt-1 text-sm text-accent" onClick={() => setProgress(100)}>Marcar como concluído</button>
          </Field>
        )}
        <Field label="Data" hint="Vazio = hoje">
          <input type="date" max={ctx.data?.today} className={inputCls} value={date} onChange={(e) => setDate(e.target.value)} />
        </Field>
        <Field label="O que você estudou?">
          <textarea className={inputCls} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
    </Sheet>
  );
}

// ------------------------------------------------------------------ project
export function ProjectSheet({ project, onClose }: { project: Project | null; onClose: () => void }) {
  const act = useAct();
  const [f, setF] = useState({
    name: project?.name ?? "", description: project?.description ?? "",
    status: project?.status ?? "active", area: project?.area ?? "work",
  });
  const [del, setDel] = useState(false);
  const save = async () => {
    const body = { ...f, description: f.description || null };
    const r = await act(
      () => (project ? api.patch(`/projects/${project.id}`, { ...body, version: project.version }) : api.post("/projects", body)),
      project ? "Projeto atualizado" : "Projeto criado",
    );
    if (r) onClose();
  };
  const remove = async () => {
    if (!project) return;
    const r = await act(() => api.del(`/projects/${project.id}`), "Projeto excluído");
    if (r) onClose();
  };
  return (
    <Sheet open onClose={onClose} title={project ? "Editar projeto" : "Novo projeto"}
      footer={
        <div className="flex gap-2">
          {project && <Button variant="danger" onClick={del ? remove : () => setDel(true)}><Trash2 className="size-4" />{del ? "Confirmar" : ""}</Button>}
          <Button className="flex-1" onClick={save} disabled={!f.name.trim()}>{project ? "Salvar" : "Criar projeto"}</Button>
        </div>
      }>
      <div className="space-y-4 pt-1">
        <input autoFocus={!project} className="w-full bg-transparent text-xl font-semibold tracking-tight outline-none placeholder:text-faint" placeholder="Nome do projeto" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <Field label="Área">
          <Segmented value={f.area} onChange={(v) => setF({ ...f, area: v })} options={[{ value: "work", label: "Trabalho" }, { value: "personal", label: "Pessoal" }, { value: "study", label: "Estudo" }, { value: "health", label: "Saúde" }]} />
        </Field>
        <Field label="Status">
          <Segmented value={f.status} onChange={(v) => setF({ ...f, status: v })} options={[{ value: "active", label: "Ativo" }, { value: "paused", label: "Pausado" }, { value: "done", label: "Concluído" }, { value: "archived", label: "Arquivado" }]} />
        </Field>
        <Field label="Descrição / contexto" hint="O Claude lê isto para entender o projeto.">
          <textarea className={inputCls} rows={4} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
        </Field>
      </div>
    </Sheet>
  );
}

// ------------------------------------------------------------------ routine
export function RoutineSheet({ routine, onClose }: { routine: Routine | null; onClose: () => void }) {
  const act = useAct();
  const [f, setF] = useState({
    name: routine?.name ?? "", description: routine?.description ?? "",
    target_per_week: routine?.target_per_week ?? 3, duration_minutes: routine?.duration_minutes ?? 60,
    preferred_days: routine?.preferred_days ?? [], preferred_start: routine?.preferred_start ?? "", preferred_end: routine?.preferred_end ?? "",
    notes: routine?.notes ?? "", active: routine?.active ?? true,
    workouts: (routine?.workouts ?? []) as Workout[],
  });
  const [del, setDel] = useState(false);
  const toggleDay = (d: number) => setF((s) => ({ ...s, preferred_days: s.preferred_days.includes(d) ? s.preferred_days.filter((x) => x !== d) : [...s.preferred_days, d].sort() }));
  const save = async () => {
    const body = {
      ...f, description: f.description || null, notes: f.notes || null,
      preferred_start: f.preferred_start || null, preferred_end: f.preferred_end || null,
      workouts: f.workouts.map((w) => ({ ...w, exercises: w.exercises.filter((e) => e.name.trim()) })),
    };
    const r = await act(
      () => (routine ? api.patch(`/routines/${routine.id}`, { ...body, version: routine.version }) : api.post("/routines", body)),
      routine ? "Treino atualizado" : "Treino criado",
    );
    if (r) onClose();
  };
  const remove = async () => {
    if (!routine) return;
    const r = await act(() => api.del(`/routines/${routine.id}`), "Treino excluído");
    if (r) onClose();
  };
  return (
    <Sheet open wide onClose={onClose} title={routine ? "Editar treino" : "Novo treino"}
      footer={
        <div className="flex gap-2">
          {routine && <Button variant="danger" onClick={del ? remove : () => setDel(true)}><Trash2 className="size-4" />{del ? "Confirmar" : ""}</Button>}
          <Button className="flex-1" onClick={save} disabled={!f.name.trim()}>{routine ? "Salvar" : "Criar treino"}</Button>
        </div>
      }>
      <div className="space-y-4 pt-1">
        <input autoFocus={!routine} className="w-full bg-transparent text-xl font-semibold tracking-tight outline-none placeholder:text-faint" placeholder="Ex.: Jiu-Jitsu, Academia" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <div className="grid grid-cols-2 gap-3">
          <Field label="Vezes por semana">
            <div className="flex items-center rounded-xl border border-line bg-surface">
              <button type="button" className="h-11 w-11 text-lg text-muted" onClick={() => setF({ ...f, target_per_week: Math.max(0, f.target_per_week - 1) })}>−</button>
              <span className="flex-1 text-center font-semibold tabular-nums">{f.target_per_week}</span>
              <button type="button" className="h-11 w-11 text-lg text-muted" onClick={() => setF({ ...f, target_per_week: Math.min(21, f.target_per_week + 1) })}>+</button>
            </div>
          </Field>
          <Field label="Duração (min)">
            <input type="number" inputMode="numeric" className={inputCls} value={f.duration_minutes} onChange={(e) => setF({ ...f, duration_minutes: Number(e.target.value) })} />
          </Field>
        </div>
        <Field label="Dias preferidos">
          <div className="flex gap-1.5">
            {WEEKDAYS.map((d, i) => (
              <button key={d} type="button" onClick={() => toggleDay(i)} className={cx("h-10 flex-1 rounded-lg text-xs font-medium transition", f.preferred_days.includes(i) ? "bg-ink text-inkfg" : "bg-surface2 text-muted")}>{d}</button>
            ))}
          </div>
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Horário preferido (início)"><input type="time" className={inputCls} value={f.preferred_start} onChange={(e) => setF({ ...f, preferred_start: e.target.value })} /></Field>
          <Field label="Até (fim)"><input type="time" className={inputCls} value={f.preferred_end} onChange={(e) => setF({ ...f, preferred_end: e.target.value })} /></Field>
        </div>
        <div>
          <p className="mb-1 text-[13px] font-medium text-muted">Exercícios</p>
          <p className="mb-3 text-xs text-faint">Monte o plano (A, B, C…). A cada sessão você marca o que foi feito e o que não foi.</p>
          <WorkoutPlanEditor value={f.workouts} onChange={(workouts) => setF((s) => ({ ...s, workouts }))} />
        </div>
        <Field label="Observações"><textarea className={inputCls} rows={3} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} placeholder="Ex.: Aula às terças e quintas, levar kimono…" /></Field>
        <div className="flex items-center justify-between rounded-xl bg-surface2 px-4 py-3">
          <span>Ativo</span><Toggle checked={f.active} onChange={(v) => setF({ ...f, active: v })} label="Ativo" />
        </div>
      </div>
    </Sheet>
  );
}

// ------------------------------------------------------------------ quick add
export function QuickAddSheet({ onPick, onClose }: { onPick: (k: "task" | "fixed" | "block") => void; onClose: () => void }) {
  const items = [
    { k: "task" as const, icon: <CheckSquare className="size-5" />, title: "Tarefa", hint: "Algo a fazer, com ou sem prazo" },
    { k: "fixed" as const, icon: <Lock className="size-5" />, title: "Evento fixo", hint: "Reunião, aula, compromisso" },
    { k: "block" as const, icon: <Move className="size-5" />, title: "Bloco flexível", hint: "Tempo reservado que o Claude pode mover" },
  ];
  return (
    <Sheet open onClose={onClose} title="Adicionar">
      <div className="space-y-2 pb-2 pt-1">
        {items.map((i) => (
          <button key={i.k} onClick={() => onPick(i.k)} className="flex w-full items-center gap-4 rounded-2xl border border-line bg-surface p-4 text-left transition hover:bg-surface2 active:scale-[.99]">
            <span className="grid size-11 place-items-center rounded-xl bg-surface2">{i.icon}</span>
            <span><span className="block font-medium">{i.title}</span><span className="text-sm text-muted">{i.hint}</span></span>
          </button>
        ))}
      </div>
    </Sheet>
  );
}

