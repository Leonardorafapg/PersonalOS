"use client";

import { ArrowDown, ArrowUp, Dumbbell, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import type { Exercise, Workout } from "@/lib/types";
import { Button, cx, inputCls } from "../ui";

const mini = `${inputCls} !px-2.5 !py-2 text-sm`;

/** Edits a routine's exercise plan: several named workouts (A/B/C…), each with an ordered list of exercises. */
export function WorkoutPlanEditor({ value, onChange }: { value: Workout[]; onChange: (w: Workout[]) => void }) {
  const [sel, setSel] = useState(0);
  const idx = Math.min(sel, Math.max(value.length - 1, 0));
  const w = value[idx];

  const patchWorkout = (patch: Partial<Workout>) => onChange(value.map((x, i) => (i === idx ? { ...x, ...patch } : x)));
  const patchEx = (j: number, patch: Partial<Exercise>) =>
    patchWorkout({ exercises: w.exercises.map((e, k) => (k === j ? { ...e, ...patch } : e)) });
  const move = (j: number, dir: -1 | 1) => {
    const ex = [...w.exercises];
    const t = j + dir;
    if (t < 0 || t >= ex.length) return;
    [ex[j], ex[t]] = [ex[t], ex[j]];
    patchWorkout({ exercises: ex });
  };
  const addWorkout = () => {
    onChange([...value, { name: value.length ? `Treino ${String.fromCharCode(65 + value.length)}` : "Treino A", exercises: [] }]);
    setSel(value.length);
  };
  const removeWorkout = () => {
    onChange(value.filter((_, i) => i !== idx));
    setSel(0);
  };

  return (
    <div className="space-y-3">
      <div className="scroll-hide -mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
        {value.map((x, i) => (
          <button
            key={x.key ?? i}
            type="button"
            onClick={() => setSel(i)}
            className={cx(
              "whitespace-nowrap rounded-full border px-3.5 py-1.5 text-sm font-medium transition",
              i === idx ? "border-ink bg-ink text-inkfg" : "border-line bg-surface text-muted hover:text-text",
            )}
          >
            {x.name || "Sem nome"} <span className="opacity-60">· {x.exercises.length}</span>
          </button>
        ))}
        <button
          type="button"
          onClick={addWorkout}
          className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border border-dashed border-line px-3.5 py-1.5 text-sm text-muted hover:text-text"
        >
          <Plus className="size-3.5" /> Treino
        </button>
      </div>

      {!w ? (
        <div className="rounded-2xl border border-dashed border-line p-6 text-center">
          <Dumbbell className="mx-auto mb-2 size-6 text-faint" />
          <p className="text-sm text-muted">Monte seus treinos (A, B, C…) com os exercícios de cada um. Você marca o que foi feito a cada sessão.</p>
          <Button variant="soft" size="sm" className="mt-3" onClick={addWorkout}><Plus className="size-4" />Criar primeiro treino</Button>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-2">
            <input
              className={cx(inputCls, "font-medium")}
              placeholder="Nome do treino (ex.: Treino A · Peito e tríceps)"
              value={w.name}
              onChange={(e) => patchWorkout({ name: e.target.value })}
            />
            <button type="button" aria-label="Excluir este treino" onClick={removeWorkout} className="grid size-10 shrink-0 place-items-center rounded-xl text-muted hover:bg-danger/10 hover:text-danger">
              <Trash2 className="size-4" />
            </button>
          </div>

          <ol className="space-y-2">
            {w.exercises.map((e, j) => (
              <li key={e.key ?? `n${j}`} className="rounded-2xl border border-line bg-surface p-3">
                <div className="flex items-center gap-2">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-surface2 text-xs font-semibold text-muted">{j + 1}</span>
                  <input className={cx(inputCls, "!py-2 font-medium")} placeholder="Exercício (ex.: Supino reto)" value={e.name} onChange={(ev) => patchEx(j, { name: ev.target.value })} />
                  <div className="flex shrink-0">
                    <button type="button" aria-label="Subir" onClick={() => move(j, -1)} disabled={j === 0} className="grid size-8 place-items-center text-muted disabled:opacity-30"><ArrowUp className="size-4" /></button>
                    <button type="button" aria-label="Descer" onClick={() => move(j, 1)} disabled={j === w.exercises.length - 1} className="grid size-8 place-items-center text-muted disabled:opacity-30"><ArrowDown className="size-4" /></button>
                    <button type="button" aria-label="Remover exercício" onClick={() => patchWorkout({ exercises: w.exercises.filter((_, k) => k !== j) })} className="grid size-8 place-items-center text-muted hover:text-danger"><Trash2 className="size-4" /></button>
                  </div>
                </div>
                <div className="mt-2 grid grid-cols-4 gap-2">
                  <label className="block">
                    <span className="mb-1 block text-[11px] text-faint">Séries</span>
                    <input className={mini} type="number" inputMode="numeric" min={1} value={e.sets ?? ""} onChange={(ev) => patchEx(j, { sets: ev.target.value ? Number(ev.target.value) : undefined })} />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-[11px] text-faint">Reps</span>
                    <input className={mini} placeholder="8-12" value={e.reps ?? ""} onChange={(ev) => patchEx(j, { reps: ev.target.value || undefined })} />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-[11px] text-faint">Carga</span>
                    <input className={mini} placeholder="40kg" value={e.load ?? ""} onChange={(ev) => patchEx(j, { load: ev.target.value || undefined })} />
                  </label>
                  <label className="block">
                    <span className="mb-1 block text-[11px] text-faint">Desc. (s)</span>
                    <input className={mini} type="number" inputMode="numeric" min={0} placeholder="60" value={e.rest_seconds ?? ""} onChange={(ev) => patchEx(j, { rest_seconds: ev.target.value ? Number(ev.target.value) : undefined })} />
                  </label>
                </div>
                <input className={cx(mini, "mt-2")} placeholder="Observação (técnica, aparelho, variação…)" value={e.notes ?? ""} onChange={(ev) => patchEx(j, { notes: ev.target.value || undefined })} />
              </li>
            ))}
          </ol>
          <Button variant="soft" size="sm" onClick={() => patchWorkout({ exercises: [...w.exercises, { name: "" }] })}>
            <Plus className="size-4" /> Adicionar exercício
          </Button>
        </>
      )}
    </div>
  );
}
