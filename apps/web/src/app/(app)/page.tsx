"use client";

import { ChevronDown, Dumbbell, Inbox, Plus, Sparkles, SkipForward } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { EntryIcons, EntryMeta, TaskRow } from "@/components/items";
import { useSheets } from "@/components/sheets/host";
import { Button, Check, Chip, Empty, Ring, SectionTitle, Sheet, Spinner, cx, inputCls } from "@/components/ui";
import { setEntryStatus, toggleTask } from "@/lib/actions";
import { api } from "@/lib/api";
import { useAct, useContextQ, useNow, useSchedule, useTasks } from "@/lib/hooks";
import { dur, fmtLong, greeting, hm, minutesOf } from "@/lib/time";
import type { Entry } from "@/lib/types";

const SKIP_REASONS = ["Sem energia", "Imprevisto", "Mudou de prioridade", "Sem tempo"];

function SkipSheet({ entry, onClose }: { entry: Entry; onClose: () => void }) {
  const act = useAct();
  const [text, setText] = useState("");
  const go = async (reason: string) => {
    const r = await act(() => setEntryStatus(entry, "skipped", reason), "Marcado como pulado");
    if (r) onClose();
  };
  return (
    <Sheet open onClose={onClose} title="Por que pular?">
      <p className="mb-3 text-sm text-muted">{entry.title}. Isso ajuda o Claude a replanejar melhor.</p>
      <div className="flex flex-wrap gap-2">
        {SKIP_REASONS.map((r) => (
          <Button key={r} variant="soft" size="sm" onClick={() => go(r)}>{r}</Button>
        ))}
      </div>
      <div className="mt-4 flex gap-2 pb-2">
        <input className={inputCls} placeholder="Outro motivo…" value={text} onChange={(e) => setText(e.target.value)} />
        <Button onClick={() => go(text)} disabled={!text.trim()}>Pular</Button>
      </div>
    </Sheet>
  );
}

export default function TodayPage() {
  const sheets = useSheets();
  const act = useAct();
  const ctx = useContextQ();
  const tz = ctx.data?.timezone ?? "America/Sao_Paulo";
  const now = useNow(tz);
  const today = ctx.data?.today ?? now.date;

  const schedule = useSchedule(today, today);
  const tasksQ = useTasks({ include_done_since: today, limit: 200 });
  const [skipping, setSkipping] = useState<Entry | null>(null);
  const [showRationale, setShowRationale] = useState(false);
  const [quick, setQuick] = useState("");

  const day = schedule.data?.days[0];
  const entries = day?.entries ?? [];
  const allTasks = useMemo(() => tasksQ.data?.tasks ?? [], [tasksQ.data]);
  const relevant = useMemo(
    () =>
      allTasks.filter((t) => {
        if (t.status === "done") return t.completed_at?.slice(0, 10) === today;
        if (t.status === "cancelled") return false;
        return t.do_date === today || t.due_date === today || t.overdue || (t.do_date != null && t.do_date < today);
      }),
    [allTasks, today],
  );
  const overdue = relevant.filter((t) => t.status !== "done" && t.overdue);
  const forToday = relevant.filter((t) => t.status !== "done" && !t.overdue);
  const doneToday = relevant.filter((t) => t.status === "done");
  const inbox = allTasks.filter((t) => t.status === "inbox").length;

  const live = entries.filter((e) => e.status !== "skipped" && e.status !== "cancelled");
  const itemsDone = live.filter((e) => e.status === "done").length + doneToday.length;
  const itemsTotal = live.length + doneToday.length + overdue.length + forToday.length;
  const pct = itemsTotal ? itemsDone / itemsTotal : 0;

  const currentIdx = entries.findIndex((e) => e.status === "planned" && minutesOf(hm(e.start)) <= now.minutes && minutesOf(hm(e.end)) > now.minutes);
  const nextIdx = entries.findIndex((e) => e.status === "planned" && minutesOf(hm(e.start)) > now.minutes);
  const focusIdx = currentIdx >= 0 ? currentIdx : nextIdx;
  const focus = focusIdx >= 0 ? entries[focusIdx] : null;
  const firstUpcoming = entries.findIndex((e) => minutesOf(hm(e.end)) > now.minutes);

  const addQuick = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!quick.trim()) return;
    const r = await act(() => api.post("/tasks", { title: quick.trim(), do_date: today, status: "todo" }));
    if (r) setQuick("");
  };

  if (ctx.isLoading || schedule.isLoading) return <div className="grid place-items-center py-24"><Spinner /></div>;

  return (
    <div>
      <header className="flex items-start justify-between gap-4 pb-2 pt-2">
        <div>
          <p className="text-sm text-muted">{greeting(Number(now.hm.slice(0, 2)))}</p>
          <h1 className="text-[28px] font-semibold first-letter:uppercase leading-tight tracking-tight">{fmtLong(today)}</h1>
          <p className="mt-1 text-sm text-muted">
            {itemsTotal ? `${itemsDone} de ${itemsTotal} itens feitos` : "Dia livre"}
            {day?.stats.planned_minutes ? ` · ${dur(day.stats.planned_minutes)} planejadas` : ""}
          </p>
        </div>
        <Ring value={pct} size={68} stroke={7}>{Math.round(pct * 100)}%</Ring>
      </header>

      {day?.plan && (day.plan.summary || day.plan.rationale) && (
        <button
          onClick={() => setShowRationale((v) => !v)}
          className="mt-3 w-full rounded-2xl border border-line bg-surface p-4 text-left transition hover:bg-surface2/50"
          aria-expanded={showRationale}
        >
          <div className="flex items-start gap-3">
            <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" />
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-medium leading-snug">{day.plan.summary ?? "Plano do dia"}</p>
              {showRationale && day.plan.rationale && <p className="mt-2 text-sm leading-relaxed text-muted">{day.plan.rationale}</p>}
            </div>
            {day.plan.rationale && <ChevronDown className={cx("size-4 shrink-0 text-faint transition", showRationale && "rotate-180")} />}
          </div>
        </button>
      )}

      {focus && (
        <div className="mt-3 rounded-2xl bg-ink p-4 text-inkfg">
          <p className="text-xs font-medium uppercase tracking-wider opacity-60">{currentIdx >= 0 ? "Agora" : "A seguir"}</p>
          <div className="mt-1 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-lg font-semibold">{focus.title}</p>
              <p className="text-sm opacity-70">{hm(focus.start)}–{hm(focus.end)} · {dur(focus.minutes)}</p>
            </div>
            <button
              onClick={() => act(() => setEntryStatus(focus, "done"), "Feito!")}
              className="shrink-0 rounded-xl bg-inkfg px-4 py-2.5 text-sm font-semibold text-ink active:scale-95"
            >
              Concluir
            </button>
          </div>
        </div>
      )}

      <SectionTitle right={<button onClick={() => sheets.quickAdd(today)} className="text-sm text-muted hover:text-text">+ Adicionar</button>}>Agenda</SectionTitle>
      {day?.all_day.length ? (
        <div className="mb-2 flex flex-wrap gap-2">
          {day.all_day.map((e) => (
            <button key={e.id} onClick={() => sheets.entry(e)} className="entry rounded-full px-3 py-1 text-sm" data-cat={e.category} data-mob={e.mobility}>{e.title}</button>
          ))}
        </div>
      ) : null}
      {entries.length === 0 ? (
        <Empty title="Nada na agenda hoje" hint="Peça ao Claude para organizar o dia, ou adicione algo você mesmo." action={<Button variant="soft" size="sm" onClick={() => sheets.quickAdd(today)}><Plus className="size-4" />Adicionar</Button>} />
      ) : (
        <ol className="space-y-2">
          {entries.map((e, i) => {
            const past = i < firstUpcoming || firstUpcoming === -1;
            const done = e.status === "done";
            return (
              <li key={`${e.id}-${e.start}`}>
                {i === firstUpcoming && firstUpcoming > 0 && (
                  <div className="my-2 flex items-center gap-2 text-xs font-medium text-accent">
                    <span className="size-2 rounded-full bg-accent" />{now.hm}
                    <span className="h-px flex-1 bg-accent/40" />
                  </div>
                )}
                <div className="flex items-stretch gap-3">
                  <div className="w-11 shrink-0 pt-3 text-right text-xs tabular-nums text-muted">
                    <div className={cx("font-medium", past && !done && e.status === "planned" && "text-faint")}>{hm(e.start)}</div>
                    <div className="text-faint">{hm(e.end)}</div>
                  </div>
                  <div
                    role="button" tabIndex={0}
                    onClick={() => sheets.entry(e)}
                    onKeyDown={(ev) => ev.key === "Enter" && sheets.entry(e)}
                    className="entry flex min-w-0 flex-1 cursor-pointer items-center gap-3 px-3.5 py-3 transition active:scale-[.99]"
                    data-cat={e.category} data-mob={e.mobility} data-status={e.status}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[15px] font-medium leading-snug">{e.title} <EntryIcons e={e} /></p>
                      <EntryMeta e={e} />
                      {e.skip_reason && <p className="mt-0.5 text-xs opacity-70">Pulado: {e.skip_reason}</p>}
                      {e.overlaps_with && <p className="mt-0.5 text-xs font-medium text-danger">Sobreposto com outro item</p>}
                    </div>
                    {e.routine && e.status !== "skipped" && (
                      <button
                        onClick={(ev) => { ev.stopPropagation(); sheets.workout({ routineId: e.routine!.id, entryId: e.id, occurrenceStart: e.occurrence_start ?? e.start }); }}
                        aria-label="Abrir treino"
                        className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-black/5 px-3 text-xs font-semibold hover:bg-black/10 dark:bg-white/10"
                      >
                        <Dumbbell className="size-3.5" />Treino
                      </button>
                    )}
                    {e.status === "planned" && (
                      <button
                        onClick={(ev) => { ev.stopPropagation(); setSkipping(e); }}
                        aria-label="Pular"
                        className="grid size-9 shrink-0 place-items-center rounded-full text-muted hover:bg-black/5"
                      >
                        <SkipForward className="size-4" />
                      </button>
                    )}
                    {e.status !== "skipped" && (
                      <Check checked={done} label={done ? "Desfazer" : "Concluir"} onChange={(v) => act(() => setEntryStatus(e, v ? "done" : "planned"))} />
                    )}
                    {e.status === "skipped" && (
                      <button onClick={(ev) => { ev.stopPropagation(); act(() => setEntryStatus(e, "planned")); }} className="text-xs text-muted underline">Desfazer</button>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {day?.free_windows && day.free_windows.length > 0 && (
        <p className="mt-3 px-1 text-xs text-muted">
          Livre: {day.free_windows.map((w) => `${hm(w.start)}–${hm(w.end)}`).join(" · ")}
        </p>
      )}

      <SectionTitle
        right={inbox > 0 ? <Link href="/tarefas?tab=inbox" className="inline-flex items-center gap-1.5"><Chip tone="accent"><Inbox className="size-3" />{inbox} no inbox</Chip></Link> : null}
      >
        Tarefas
      </SectionTitle>
      <form onSubmit={addQuick} className="mb-2">
        <input className={inputCls} placeholder="Nova tarefa para hoje…" value={quick} onChange={(e) => setQuick(e.target.value)} />
      </form>
      {overdue.length + forToday.length + doneToday.length === 0 ? (
        <p className="px-1 py-4 text-sm text-muted">Nenhuma tarefa para hoje.</p>
      ) : (
        <div className="-mx-1">
          {[...overdue, ...forToday].map((t) => (
            <TaskRow key={t.id} task={t} today={today} onOpen={() => sheets.task(t)} onToggle={() => act(() => toggleTask(t))} />
          ))}
          {doneToday.length > 0 && <p className="mb-1 mt-3 px-3 text-xs font-medium uppercase tracking-wider text-faint">Concluídas hoje</p>}
          {doneToday.map((t) => (
            <TaskRow key={t.id} task={t} today={today} onOpen={() => sheets.task(t)} onToggle={() => act(() => toggleTask(t))} />
          ))}
        </div>
      )}
      {skipping && <SkipSheet entry={skipping} onClose={() => setSkipping(null)} />}
    </div>
  );
}
