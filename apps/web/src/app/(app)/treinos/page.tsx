"use client";

import { CalendarPlus, CheckCircle2, Dumbbell, Play, Plus } from "lucide-react";
import { useSheets } from "@/components/sheets/host";
import { Button, Chip, Empty, Spinner, cx } from "@/components/ui";
import { useRoutines } from "@/lib/hooks";
import { WEEKDAYS, dur, fmtShort, fromMinutes, minutesOf } from "@/lib/time";
import type { Routine } from "@/lib/types";

function Quota({ r }: { r: Routine }) {
  const done = r.done_this_week ?? 0;
  const planned = r.planned_this_week ?? 0;
  const slots = Math.max(r.target_per_week, done + planned);
  return (
    <div className="flex items-center gap-1.5" aria-label={`${done} de ${r.target_per_week} esta semana`}>
      {Array.from({ length: slots }, (_, i) => (
        <span key={i} className={cx("size-3.5 rounded-full border-[1.5px]", i < done ? "border-ok bg-ok" : i < done + planned ? "border-dashed border-accent" : "border-line")} />
      ))}
    </div>
  );
}

export default function RoutinesPage() {
  const sheets = useSheets();
  const q = useRoutines();
  const list = q.data?.routines ?? [];

  const schedule = (r: Routine) => {
    const s = r.preferred_start ?? "19:00";
    sheets.entry(null, {
      title: r.name, mobility: "flexible", category: "training", routine_id: r.id,
      start: s, end: fromMinutes(Math.min(minutesOf(s) + r.duration_minutes, 23 * 60 + 59)),
    });
  };

  return (
    <div>
      <header className="pb-3 pt-2">
        <h1 className="text-[28px] font-semibold tracking-tight">Treinos</h1>
        <p className="text-sm text-muted">Monte os exercícios, marque o que foi feito a cada sessão e acompanhe a semana.</p>
      </header>
      {q.isLoading ? <div className="grid place-items-center py-16"><Spinner /></div> : list.length === 0 ? (
        <Empty icon={<Dumbbell className="size-5" />} title="Nenhum treino cadastrado" hint="Cadastre Jiu-Jitsu, academia… Defina os exercícios e o Claude usa isso para planejar sua semana." action={<Button onClick={() => sheets.routine(null)}><Plus className="size-4" />Novo treino</Button>} />
      ) : (
        <ul className="space-y-3">
          {list.map((r) => {
            return (
              <li key={r.id} className={cx("rounded-2xl border border-line bg-surface p-4", !r.active && "opacity-60")}>
                <button onClick={() => sheets.routine(r)} className="block w-full text-left">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-[17px] font-semibold">{r.name}</p>
                    <span className="text-sm tabular-nums text-muted">{r.done_this_week ?? 0}/{r.target_per_week} na semana</span>
                  </div>
                  <div className="mt-3"><Quota r={r} /></div>
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                    <Chip>{dur(r.duration_minutes)}</Chip>
                    {r.preferred_start && <Chip>{r.preferred_start}{r.preferred_end ? `–${r.preferred_end}` : ""}</Chip>}
                    {r.preferred_days?.map((d) => <Chip key={d}>{WEEKDAYS[d]}</Chip>)}
                    {!r.active && <Chip tone="muted">inativo</Chip>}
                  </div>
                  {r.workouts && r.workouts.length > 0 ? (
                    <ul className="mt-3 space-y-1 text-sm text-muted">
                      {r.workouts.map((w) => (
                        <li key={w.key} className="flex items-center justify-between gap-3">
                          <span className="truncate text-text">{w.name}</span>
                          <span className="shrink-0 text-xs">{w.exercises.length} exercícios</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-3 text-sm text-accent">+ Cadastrar exercícios</p>
                  )}
                  {r.notes && <p className="mt-2 line-clamp-2 text-sm text-muted">{r.notes}</p>}
                </button>

                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" onClick={() => sheets.workout({ routineId: r.id })}><Play className="size-3.5" />Registrar treino</Button>
                  <Button size="sm" variant="soft" onClick={() => schedule(r)}><CalendarPlus className="size-4" />Agendar sessão</Button>
                </div>

                {r.recent_sessions && r.recent_sessions.length > 0 && (
                  <div className="mt-4 border-t border-line pt-3">
                    <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">Últimas sessões</p>
                    <ul className="space-y-1">
                      {r.recent_sessions.map((s) => (
                        <li key={s.id}>
                          <button
                            onClick={() => sheets.workout({ sessionId: s.id })}
                            className="flex w-full items-center justify-between gap-3 rounded-xl px-2 py-2 text-left text-sm transition hover:bg-surface2/60"
                          >
                            <span className="flex min-w-0 items-center gap-2">
                              {s.finished ? <CheckCircle2 className="size-4 shrink-0 text-ok" /> : <span className="size-4 shrink-0 rounded-full border border-dashed border-accent" />}
                              <span className="truncate">{s.workout_name}</span>
                              <span className="shrink-0 text-xs text-muted">{fmtShort(s.date)}</span>
                            </span>
                            <span className="shrink-0 text-xs tabular-nums">
                              <span className="text-ok">{s.summary.done}✓</span>
                              {s.summary.not_done > 0 && <span className="ml-1.5 text-danger">{s.summary.not_done}✗</span>}
                              {s.summary.pending > 0 && <span className="ml-1.5 text-muted">{s.summary.pending}…</span>}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
