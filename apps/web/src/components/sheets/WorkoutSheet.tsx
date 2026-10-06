"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown, Plus, RotateCcw, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useToast } from "@/components/providers";
import { ApiError, api } from "@/lib/api";
import { useRoutines } from "@/lib/hooks";
import { dur, fmtShort } from "@/lib/time";
import type { SessionExercise, Workout, WorkoutSession } from "@/lib/types";
import { Bar, Button, Chip, Field, Sheet, Spinner, cx, inputCls } from "../ui";

type Res = { session: WorkoutSession; entry_status?: string | null };

export type WorkoutTarget = {
  routineId?: string;
  entryId?: string;
  occurrenceStart?: string;
  sessionId?: string;
};

function planned(e: SessionExercise) {
  const bits = [
    e.sets && e.reps ? `${e.sets}×${e.reps}` : e.sets ? `${e.sets} séries` : e.reps,
    e.load,
    e.rest_seconds ? `${e.rest_seconds}s desc.` : null,
  ].filter(Boolean);
  return bits.join(" · ");
}

function ExerciseRow({
  ex, locked, onDone, onDetails,
}: {
  ex: SessionExercise;
  locked: boolean;
  onDone: (v: boolean | null) => void;
  onDetails: (patch: { actual?: string; note?: string }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [actual, setActual] = useState(ex.actual ?? "");
  const [note, setNote] = useState(ex.note ?? "");
  const meta = planned(ex);
  return (
    <li
      className={cx(
        "rounded-2xl border bg-surface transition",
        ex.done === true && "border-ok/40 bg-ok/[.06]",
        ex.done === false && "border-danger/30 bg-danger/[.05]",
        ex.done === null && "border-line",
      )}
    >
      <div className="flex items-center gap-2 p-3">
        <button type="button" onClick={() => setOpen((v) => !v)} className="min-w-0 flex-1 text-left" aria-expanded={open}>
          <p className={cx("flex items-center gap-1.5 text-[15px] font-medium leading-snug", ex.done === false && "text-muted line-through")}>
            <span className="truncate">{ex.name}</span>
            {ex.extra && <Chip className="shrink-0">extra</Chip>}
            <ChevronDown className={cx("size-3.5 shrink-0 text-faint transition", open && "rotate-180")} />
          </p>
          {(meta || ex.actual) && (
            <p className="mt-0.5 truncate text-xs text-muted">
              {meta}
              {ex.actual && <span className="text-text"> {meta ? "→" : ""} {ex.actual}</span>}
            </p>
          )}
        </button>
        <div className="flex shrink-0 gap-2" role="group" aria-label={`Marcar ${ex.name}`}>
          <button
            type="button" disabled={locked} aria-pressed={ex.done === true} aria-label="Feito"
            onClick={() => onDone(ex.done === true ? null : true)}
            className={cx(
              "grid size-11 place-items-center rounded-full border-[1.5px] transition active:scale-90 disabled:opacity-60",
              ex.done === true ? "border-transparent bg-ok text-white" : "border-line text-faint hover:border-ok hover:text-ok",
            )}
          >
            <Check className="size-5" strokeWidth={2.6} />
          </button>
          <button
            type="button" disabled={locked} aria-pressed={ex.done === false} aria-label="Não fiz"
            onClick={() => onDone(ex.done === false ? null : false)}
            className={cx(
              "grid size-11 place-items-center rounded-full border-[1.5px] transition active:scale-90 disabled:opacity-60",
              ex.done === false ? "border-transparent bg-danger text-white" : "border-line text-faint hover:border-danger hover:text-danger",
            )}
          >
            <X className="size-5" strokeWidth={2.6} />
          </button>
        </div>
      </div>
      {open && (
        <div className="space-y-2 border-t border-line/70 px-3 pb-3 pt-2.5">
          {ex.notes && <p className="text-xs text-muted">📌 {ex.notes}</p>}
          <input
            className={cx(inputCls, "!py-2 text-sm")} placeholder="O que você fez de fato? (ex.: 4×8 com 62kg)"
            value={actual} disabled={locked}
            onChange={(e) => setActual(e.target.value)}
            onBlur={() => actual !== (ex.actual ?? "") && onDetails({ actual })}
          />
          <input
            className={cx(inputCls, "!py-2 text-sm")} placeholder="Observação (dor, dificuldade, troca de aparelho…)"
            value={note} disabled={locked}
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => note !== (ex.note ?? "") && onDetails({ note })}
          />
        </div>
      )}
    </li>
  );
}

export function WorkoutSheet({ target, onClose }: { target: WorkoutTarget; onClose: () => void }) {
  const toast = useToast();
  const qc = useQueryClient();
  const routines = useRoutines();
  const [session, setSessionState] = useState<WorkoutSession | null>(null);
  const latest = useRef<WorkoutSession | null>(null); // always the newest server state (versions!)
  const queue = useRef<Promise<void>>(Promise.resolve());
  const setSession = (s: WorkoutSession | null) => {
    latest.current = s;
    setSessionState(s);
  };
  const [picking, setPicking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState("");
  const started = useRef(false);
  const changed = useRef(false);

  const routine = routines.data?.routines.find((r) => r.id === (target.routineId ?? session?.routine_id));

  const begin = async (workoutKey?: string) => {
    try {
      const r = await api.post<Res>("/workouts", {
        routine_id: target.routineId ?? null,
        workout_key: workoutKey ?? null,
        entry_id: target.entryId ?? null,
        occurrence_start: target.occurrenceStart ?? null,
      });
      changed.current = true;
      setPicking(false);
      setSession(r.session);
    } catch (e) {
      if (e instanceof ApiError && e.message.includes("workout_key")) setPicking(true);
      else {
        toast.error(e);
        onClose();
      }
    }
  };

  useEffect(() => {
    if (started.current) return;
    if (!target.sessionId && !routines.data) return;
    started.current = true;
    (async () => {
      if (target.sessionId) {
        try {
          const r = await api.get<Res>(`/workouts/${target.sessionId}`);
          setSession(r.session);
        } catch (e) {
          toast.error(e);
          onClose();
        }
      } else {
        await begin();
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routines.data]);

  const close = () => {
    if (changed.current) qc.invalidateQueries();
    onClose();
  };

  // Updates are applied one at a time with the newest version, so fast taps never collide (STALE_VERSION).
  const patch = (body: Record<string, unknown>, okMsg?: string) => {
    const run = async () => {
      const cur = latest.current;
      if (!cur) return;
      setBusy(true);
      try {
        const r = await api.patch<Res>(`/workouts/${cur.id}`, { ...body, version: cur.version });
        setSession(r.session);
        changed.current = true;
        if (okMsg) toast.show(okMsg);
      } catch (e) {
        toast.error(e);
        try {
          const r = await api.get<Res>(`/workouts/${cur.id}`); // resync after a failure
          setSession(r.session);
        } catch { /* ignore */ }
      } finally {
        setBusy(false);
      }
    };
    queue.current = queue.current.then(run);
    return queue.current;
  };

  // instant feedback for the done / not-done taps; the server response replaces it
  const mark = (key: string, v: boolean | null) => {
    const cur = latest.current;
    if (cur?.exercises) {
      const exs = cur.exercises.map((e) => (e.key === key ? { ...e, done: v } : e));
      const done = exs.filter((e) => e.done === true).length;
      const notDone = exs.filter((e) => e.done === false).length;
      setSessionState({ ...cur, exercises: exs, summary: { total: exs.length, done, not_done: notDone, pending: exs.length - done - notDone } });
    }
    patch({ exercises: [{ key, done: v }] });
  };

  const exercises = session?.exercises ?? [];
  const s = session?.summary;
  const handled = s ? s.done + s.not_done : 0;
  const pct = s && s.total ? (s.done / s.total) * 100 : 0;
  const locked = !!session?.finished;

  const title = session ? session.workout_name : "Treino";

  return (
    <Sheet
      open
      onClose={close}
      wide
      title={title}
      footer={
        session ? (
          session.finished ? (
            <div className="flex gap-2">
              <Button variant="soft" onClick={() => patch({ finished: false })} loading={busy}><RotateCcw className="size-4" />Reabrir</Button>
              <Button className="flex-1" onClick={close}>Pronto</Button>
            </div>
          ) : (
            <div className="space-y-2">
              {s && s.pending > 0 && <p className="text-center text-xs text-muted">{s.pending} pendente{s.pending > 1 ? "s" : ""} serão marcados como “não feito”.</p>}
              <Button className="w-full" loading={busy} onClick={() => patch({ finished: true }, "Treino finalizado")}>Finalizar treino</Button>
            </div>
          )
        ) : undefined
      }
    >
      {!session && !picking && <div className="grid place-items-center py-16"><Spinner /></div>}

      {picking && (
        <div className="space-y-2 pb-2 pt-1">
          <p className="text-sm text-muted">Qual treino você vai fazer?</p>
          {(routine?.workouts ?? []).map((w: Workout) => (
            <button
              key={w.key} onClick={() => begin(w.key)}
              className="flex w-full items-center justify-between rounded-2xl border border-line bg-surface p-4 text-left transition hover:bg-surface2 active:scale-[.99]"
            >
              <span className="font-medium">{w.name}</span>
              <span className="text-sm text-muted">{w.exercises.length} exercícios</span>
            </button>
          ))}
        </div>
      )}

      {session && (
        <div className="space-y-4 pt-1">
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted">
            <span>{session.routine_name ?? routine?.name}</span>
            <span>·</span>
            <span>{fmtShort(session.date)}</span>
            {session.finished && <Chip tone="ok">finalizado</Chip>}
          </div>

          {s && s.total > 0 && (
            <div>
              <div className="mb-1.5 flex items-baseline justify-between text-sm">
                <span><b className="tabular-nums">{s.done}</b> de {s.total} feitos</span>
                {s.not_done > 0 && <span className="text-danger">{s.not_done} não feito{s.not_done > 1 ? "s" : ""}</span>}
              </div>
              <Bar value={pct} tone="ok" className="h-2" />
              {handled === s.total && !session.finished && <p className="mt-1.5 text-xs text-muted">Tudo marcado. Toque em “Finalizar treino”.</p>}
            </div>
          )}

          {exercises.length === 0 ? (
            <p className="rounded-2xl bg-surface2 p-4 text-sm text-muted">
              Este treino não tem exercícios cadastrados. Adicione abaixo, ou monte o plano em Treinos → Editar.
            </p>
          ) : (
            <ul className="space-y-2">
              {exercises.map((ex) => (
                <ExerciseRow
                  key={ex.key} ex={ex} locked={locked}
                  onDone={(v) => mark(ex.key, v)}
                  onDetails={(d) => patch({ exercises: [{ key: ex.key, ...d }] })}
                />
              ))}
            </ul>
          )}

          {!locked && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const name = adding.trim();
                if (!name) return;
                setAdding("");
                patch({ exercises: [{ name, done: true }] });
              }}
              className="flex gap-2"
            >
              <input className={inputCls} placeholder="Fez algo a mais? Adicionar exercício" value={adding} onChange={(e) => setAdding(e.target.value)} />
              <Button type="submit" variant="soft" aria-label="Adicionar" disabled={!adding.trim()}><Plus className="size-4" /></Button>
            </form>
          )}

          <div className="grid grid-cols-2 gap-3">
            <Field label={`Esforço percebido${session.effort ? ` · ${session.effort}/10` : ""}`}>
              <input
                type="range" min={1} max={10} step={1} disabled={locked && false}
                value={session.effort ?? 5} className="w-full accent-[var(--ink)]"
                onChange={(e) => setSession({ ...session, effort: Number(e.target.value) })}
                onPointerUp={(e) => patch({ effort: Number((e.target as HTMLInputElement).value) })}
                onKeyUp={(e) => patch({ effort: Number((e.target as HTMLInputElement).value) })}
              />
            </Field>
            <Field label="Duração (min)" hint={session.duration_minutes ? dur(session.duration_minutes) : undefined}>
              <input
                type="number" inputMode="numeric" min={1} className={inputCls}
                defaultValue={session.duration_minutes ?? ""} key={`d${session.version}`}
                onBlur={(e) => e.target.value && Number(e.target.value) !== session.duration_minutes && patch({ duration_minutes: Number(e.target.value) })}
              />
            </Field>
          </div>
          <Field label="Como foi o treino?">
            <textarea
              className={inputCls} rows={3} defaultValue={session.notes ?? ""} key={`n${session.version}`}
              onBlur={(e) => e.target.value !== (session.notes ?? "") && patch({ notes: e.target.value })}
            />
          </Field>
        </div>
      )}
    </Sheet>
  );
}
