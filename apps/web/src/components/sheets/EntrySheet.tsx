"use client";

import { Dumbbell, Lock, Move, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { CATEGORIES, buildRRule, parseRRule, type Recurrence } from "@/lib/entry";
import { useAct, useContextQ, useRoadmap, useRoutines, useTasks } from "@/lib/hooks";
import { flattenTopics } from "@/lib/study";
import { WEEKDAYS, fromMinutes, hm, minutesOf, nowIn, ymd } from "@/lib/time";
import type { Category, Entry, EntryStatus, Mobility } from "@/lib/types";
import { Button, ClaudeBadge, Field, Segmented, Sheet, Toggle, cx, inputCls } from "../ui";
import { useSheets } from "./host";

export type EntryDefaults = Partial<{
  title: string; mobility: Mobility; category: Category; date: string; start: string; end: string;
  task_id: string; study_topic_id: string; routine_id: string;
}>;

export function EntrySheet({ entry, defaults, onClose }: { entry: Entry | null; defaults?: EntryDefaults; onClose: () => void }) {
  const act = useAct();
  const sheets = useSheets();
  const ctx = useContextQ();
  const tasks = useTasks({ status: ["inbox", "todo", "doing"], limit: 200 });
  const roadmap = useRoadmap();
  const routines = useRoutines();
  const today = ctx.data?.today ?? new Date().toISOString().slice(0, 10);
  const isException = !!entry?.series_id;
  const isRecurring = !!entry?.recurring || isException;
  const [scope, setScope] = useState<"this" | "all">(isException ? "this" : "all");

  const [f, setF] = useState(() => {
    const date = entry ? ymd(entry.start) : defaults?.date ?? today;
    const nxt = nowIn(ctx.data?.timezone ?? "America/Sao_Paulo");
    const nextSlot = fromMinutes(Math.min(Math.ceil((nxt.minutes + 1) / 30) * 30, 22 * 60));
    const startHm = entry ? hm(entry.start) : defaults?.start ?? (date === nxt.date ? nextSlot : "09:00");
    const endHm = entry ? hm(entry.end) : defaults?.end ?? fromMinutes(Math.min(minutesOf(startHm) + 60, 23 * 60 + 59));
    return {
      title: entry?.title ?? defaults?.title ?? "",
      mobility: (entry?.mobility ?? defaults?.mobility ?? "fixed") as Mobility,
      category: (entry?.category ?? defaults?.category ?? "other") as Category,
      all_day: !!entry?.all_day,
      date: entry ? ymd(entry.start) : defaults?.date ?? today,
      endDate: entry ? ymd(entry.end) : defaults?.date ?? today,
      start: startHm,
      end: endHm,
      status: (entry?.status ?? "planned") as EntryStatus,
      skip_reason: entry?.skip_reason ?? "",
      location: entry?.location ?? "",
      notes: entry?.notes ?? "",
      task_id: entry?.task?.id ?? defaults?.task_id ?? "",
      study_topic_id: entry?.study_topic?.id ?? defaults?.study_topic_id ?? "",
      routine_id: entry?.routine?.id ?? defaults?.routine_id ?? "",
      rec: parseRRule(entry?.rrule) as Recurrence,
    };
  });
  const [delStep, setDelStep] = useState<0 | 1>(0);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));
  const topics = useMemo(() => flattenTopics(roadmap.data?.roots).filter((t) => t.leaf), [roadmap.data]);

  const changeStart = (v: string) => {
    const dur = Math.max(5, minutesOf(f.end) - minutesOf(f.start));
    setF((s) => ({ ...s, start: v, end: fromMinutes(Math.min(minutesOf(v) + dur, 23 * 60 + 59)) }));
  };

  const save = async () => {
    const startISO = f.all_day ? `${f.date}T00:00` : `${f.date}T${f.start}`;
    const endISO = f.all_day ? `${f.endDate >= f.date ? f.endDate : f.date}T00:00` : `${f.date}T${f.end}`;
    const body: Record<string, unknown> = {
      title: f.title.trim(),
      mobility: f.mobility,
      category: f.category,
      all_day: f.all_day,
      start: startISO,
      end: endISO,
      status: f.status,
      skip_reason: f.status === "skipped" ? f.skip_reason || null : null,
      location: f.location || null,
      notes: f.notes || null,
      task_id: f.task_id || null,
      study_topic_id: f.study_topic_id || null,
      routine_id: f.routine_id || null,
    };
    if (!isRecurring || (scope === "all" && !isException)) {
      const rule = buildRRule(f.rec);
      if (rule !== (entry?.rrule ?? null)) body.rrule = rule;
    }
    let req: () => Promise<unknown>;
    if (!entry) {
      req = () => api.post("/calendar", body);
    } else if (entry.recurring && !isException) {
      // virtual occurrence of a series: id = series, occurrence_start identifies which one
      req = () =>
        api.patch(`/calendar/${entry.id}`, {
          ...body, version: entry.version, scope, occurrence_start: entry.occurrence_start ?? entry.start,
        });
    } else {
      req = () => api.patch(`/calendar/${entry.id}`, { ...body, version: entry.version });
    }
    const r = await act(req, entry ? "Atualizado" : "Criado");
    if (r) onClose();
  };

  const remove = async (s: "this" | "all") => {
    if (!entry) return;
    const params: Record<string, unknown> = {};
    if (entry.recurring && !isException) {
      params.scope = s;
      params.occurrence_start = entry.occurrence_start ?? entry.start;
    }
    const r = await act(() => api.del(`/calendar/${entry.id}`, params), "Excluído");
    if (r) onClose();
  };

  const recurDays = (d: number) =>
    set("rec", { ...f.rec, days: f.rec.days.includes(d) ? f.rec.days.filter((x) => x !== d) : [...f.rec.days, d].sort() });

  return (
    <Sheet
      open
      onClose={onClose}
      title={entry ? "Editar" : f.mobility === "fixed" ? "Novo evento" : "Novo bloco"}
      footer={
        delStep === 1 && entry ? (
          <div className="space-y-2">
            <p className="text-center text-sm text-muted">Excluir &ldquo;{entry.title}&rdquo;?</p>
            <div className="flex gap-2">
              <Button variant="soft" onClick={() => setDelStep(0)}>Cancelar</Button>
              {entry.recurring && !isException ? (
                <>
                  <Button variant="danger" className="flex-1" onClick={() => remove("this")}>Só esta</Button>
                  <Button variant="danger" className="flex-1" onClick={() => remove("all")}>Toda a série</Button>
                </>
              ) : (
                <Button variant="danger" className="flex-1" onClick={() => remove("all")}>Excluir</Button>
              )}
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            {entry && (
              <Button variant="danger" onClick={() => setDelStep(1)} aria-label="Excluir"><Trash2 className="size-4" /></Button>
            )}
            <Button className="flex-1" onClick={save} disabled={!f.title.trim()}>{entry ? "Salvar" : "Criar"}</Button>
          </div>
        )
      }
    >
      <div className="space-y-4 pt-1">
        <input
          autoFocus={!entry}
          className="w-full bg-transparent text-xl font-semibold tracking-tight outline-none placeholder:text-faint"
          placeholder={f.mobility === "fixed" ? "Título do evento" : "O que vai fazer neste bloco?"}
          value={f.title}
          onChange={(e) => set("title", e.target.value)}
        />
        {entry?.created_by === "claude" && (
          <p className="flex items-center gap-1 text-xs text-muted"><ClaudeBadge /> criado pelo Claude</p>
        )}
        {entry?.routine && (
          <Button
            variant="soft" className="w-full"
            onClick={() => sheets.workout({ routineId: entry.routine!.id, entryId: entry.id, occurrenceStart: entry.occurrence_start ?? entry.start })}
          >
            <Dumbbell className="size-4" /> Abrir treino · marcar exercícios
          </Button>
        )}

        <div>
          <Segmented
            value={f.mobility}
            onChange={(v) => set("mobility", v)}
            options={[
              { value: "fixed", label: <span className="inline-flex items-center gap-1.5"><Lock className="size-3.5" />Fixo</span> },
              { value: "flexible", label: <span className="inline-flex items-center gap-1.5"><Move className="size-3.5" />Flexível</span> },
            ]}
          />
          <p className="mt-1.5 px-1 text-xs text-faint">
            {f.mobility === "fixed"
              ? "Compromisso real: o Claude não move nem apaga sem você pedir."
              : "Bloco planejado: o Claude pode reorganizar quando precisar."}
          </p>
        </div>

        {isRecurring && !isException && (
          <Field label="Aplicar a">
            <Segmented value={scope} onChange={setScope} options={[{ value: "this", label: "Só esta ocorrência" }, { value: "all", label: "Toda a série" }]} />
          </Field>
        )}

        <div className="flex items-center justify-between rounded-xl bg-surface2 px-4 py-3">
          <span className="text-[15px]">Dia inteiro</span>
          <Toggle checked={f.all_day} onChange={(v) => set("all_day", v)} label="Dia inteiro" />
        </div>

        {f.all_day ? (
          <div className="grid grid-cols-2 gap-3">
            <Field label="De">
              <input type="date" className={inputCls} value={f.date} onChange={(e) => setF((s) => ({ ...s, date: e.target.value, endDate: s.endDate < e.target.value ? e.target.value : s.endDate }))} />
            </Field>
            <Field label="Até (inclusive)">
              <input type="date" className={inputCls} min={f.date} value={f.endDate} onChange={(e) => set("endDate", e.target.value)} />
            </Field>
          </div>
        ) : (
          <>
            <Field label="Data">
              <input type="date" className={inputCls} value={f.date} onChange={(e) => set("date", e.target.value)} />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Início">
                <input type="time" className={inputCls} value={f.start} onChange={(e) => changeStart(e.target.value)} />
              </Field>
              <Field label="Fim">
                <input type="time" className={inputCls} value={f.end} onChange={(e) => set("end", e.target.value)} />
              </Field>
            </div>
          </>
        )}

        <Field label="Categoria">
          <div className="flex flex-wrap gap-1.5">
            {CATEGORIES.map((c) => (
              <button
                key={c.value}
                type="button"
                onClick={() => set("category", c.value)}
                className={cx(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition",
                  f.category === c.value ? "border-ink bg-ink text-inkfg" : "border-line bg-surface text-muted hover:text-text",
                )}
              >
                <span className="size-2 rounded-full" style={{ background: `var(--c-${c.value})` }} />
                {c.label}
              </button>
            ))}
          </div>
        </Field>

        {(!isRecurring || (scope === "all" && !isException)) && (
          <Field label="Repetir">
            <select
              className={inputCls}
              value={f.rec.kind}
              onChange={(e) => set("rec", { ...f.rec, kind: e.target.value as Recurrence["kind"], days: e.target.value === "weekly" && !f.rec.days.length ? [0] : f.rec.days })}
            >
              <option value="none">Não repete</option>
              <option value="daily">Todos os dias</option>
              <option value="weekdays">Dias úteis</option>
              <option value="weekly">Toda semana em…</option>
              <option value="monthly">Todo mês</option>
              <option value="custom">Personalizado (RRULE)</option>
            </select>
            {f.rec.kind === "weekly" && (
              <div className="mt-2 flex gap-1.5">
                {WEEKDAYS.map((d, i) => (
                  <button
                    key={d} type="button" onClick={() => recurDays(i)}
                    className={cx("h-9 flex-1 rounded-lg text-xs font-medium transition", f.rec.days.includes(i) ? "bg-ink text-inkfg" : "bg-surface2 text-muted")}
                  >
                    {d}
                  </button>
                ))}
              </div>
            )}
            {f.rec.kind === "custom" && (
              <input className={cx(inputCls, "mt-2 font-mono text-sm")} placeholder="FREQ=WEEKLY;INTERVAL=2;BYDAY=MO" value={f.rec.raw} onChange={(e) => set("rec", { ...f.rec, raw: e.target.value })} />
            )}
          </Field>
        )}

        {entry && (
          <Field label="Situação">
            <Segmented
              value={f.status}
              onChange={(v) => set("status", v)}
              options={[{ value: "planned", label: "Planejado" }, { value: "done", label: "Feito" }, { value: "skipped", label: "Pulado" }]}
            />
            {f.status === "skipped" && (
              <input className={cx(inputCls, "mt-2")} placeholder="Motivo (opcional)" value={f.skip_reason} onChange={(e) => set("skip_reason", e.target.value)} />
            )}
          </Field>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Tarefa vinculada">
            <select className={inputCls} value={f.task_id} onChange={(e) => set("task_id", e.target.value)}>
              <option value="">—</option>
              {entry?.task && !tasks.data?.tasks.some((t) => t.id === entry.task!.id) && <option value={entry.task.id}>{entry.task.name}</option>}
              {tasks.data?.tasks.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
            </select>
          </Field>
          <Field label="Tópico de estudo">
            <select className={inputCls} value={f.study_topic_id} onChange={(e) => set("study_topic_id", e.target.value)}>
              <option value="">—</option>
              {topics.map((t) => <option key={t.id} value={t.id}>{t.path}</option>)}
            </select>
          </Field>
          <Field label="Rotina / treino">
            <select className={inputCls} value={f.routine_id} onChange={(e) => set("routine_id", e.target.value)}>
              <option value="">—</option>
              {routines.data?.routines.filter((r) => r.active || r.id === f.routine_id).map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
            </select>
          </Field>
          <Field label="Local">
            <input className={inputCls} value={f.location} onChange={(e) => set("location", e.target.value)} />
          </Field>
        </div>
        <Field label="Notas">
          <textarea className={inputCls} rows={2} value={f.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>
      </div>
    </Sheet>
  );
}
