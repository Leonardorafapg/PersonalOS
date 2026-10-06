"use client";

import { Activity, Sparkles, Undo2, User } from "lucide-react";
import { useState } from "react";
import { Button, Chip, Empty, Segmented, Spinner, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { useAct, useContextQ, useOps } from "@/lib/hooks";
import { fmtShort, hm, ymd } from "@/lib/time";
import type { OpBatch } from "@/lib/types";

const TOOL: Record<string, string> = {
  save_tasks: "Tarefas", save_calendar_entries: "Agenda", set_day_plan: "Plano do dia", save_projects: "Projetos",
  save_study_topics: "Roadmap de estudos", log_study: "Registro de estudo", save_routines: "Treinos",
  save_preferences: "Preferências", log_workout: "Treino", delete_entity: "Exclusão", undo_operation: "Desfazer",
};
const ACTION: Record<string, string> = { create: "criou", update: "alterou", delete: "excluiu", restore: "restaurou", reject: "recusado" };

function Batch({ b, today, onUndo }: { b: OpBatch; today: string; onUndo: () => void }) {
  const [more, setMore] = useState(false);
  const rejected = b.result === "rejected";
  const canUndo = !rejected && !b.undone_by && b.tool !== "undo_operation";
  const shown = more ? b.changes : b.changes.slice(0, 4);
  return (
    <li className={cx("rounded-2xl border bg-surface p-4", rejected ? "border-danger/30" : "border-line", b.undone_by && "opacity-55")}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className={cx("grid size-8 shrink-0 place-items-center rounded-full", b.actor === "claude" ? "bg-accent/12 text-accent" : "bg-surface2 text-muted")}>
            {b.actor === "claude" ? <Sparkles className="size-4" /> : <User className="size-4" />}
          </span>
          <div className="min-w-0">
            <p className="truncate font-medium">{TOOL[b.tool] ?? b.tool}</p>
            <p className="text-xs text-muted">
              {b.actor === "claude" ? "Claude" : b.actor === "system" ? "Sistema" : "Você"} · {ymd(b.ts) === today ? "hoje" : fmtShort(ymd(b.ts))} {hm(b.ts)}
              {b.undone_by && " · desfeito"}
            </p>
          </div>
        </div>
        {canUndo && <Button size="sm" variant="soft" onClick={onUndo}><Undo2 className="size-3.5" />Desfazer</Button>}
        {rejected && <Chip tone="danger">recusado</Chip>}
      </div>
      <ul className="mt-3 space-y-1 text-sm">
        {shown.map((c, i) => (
          <li key={i} className="flex gap-2 text-muted">
            <span className="w-16 shrink-0 text-xs uppercase tracking-wide text-faint">{ACTION[c.action] ?? c.action}</span>
            <span className="min-w-0 flex-1 truncate text-text">{c.error ? `${c.error}: ` : ""}{c.summary}</span>
          </li>
        ))}
      </ul>
      {b.changes.length > 4 && (
        <button onClick={() => setMore((v) => !v)} className="mt-2 text-xs text-muted underline">{more ? "Mostrar menos" : `+${b.changes.length - 4} mudanças`}</button>
      )}
    </li>
  );
}

export default function ActivityPage() {
  const act = useAct();
  const ctx = useContextQ();
  const [who, setWho] = useState<"all" | "claude" | "manual">("all");
  const q = useOps(who === "all" ? undefined : who);
  const today = ctx.data?.today ?? "";
  return (
    <div>
      <header className="pb-3 pt-2">
        <h1 className="text-[28px] font-semibold tracking-tight">Atividade</h1>
        <p className="text-sm text-muted">Tudo que foi alterado, por quem e quando. Cada mudança pode ser desfeita.</p>
      </header>
      <Segmented value={who} onChange={setWho} options={[{ value: "all", label: "Tudo" }, { value: "claude", label: "Claude" }, { value: "manual", label: "Você" }]} />
      {q.isLoading ? <div className="grid place-items-center py-16"><Spinner /></div> : !q.data?.batches.length ? (
        <Empty icon={<Activity className="size-5" />} title="Sem atividade" hint="As alterações aparecem aqui assim que acontecerem." />
      ) : (
        <ul className="mt-4 space-y-3">
          {q.data.batches.map((b) => (
            <Batch key={b.batch_id} b={b} today={today} onUndo={() => act(() => api.post(`/operations/${b.batch_id}/undo`), "Alteração desfeita")} />
          ))}
        </ul>
      )}
    </div>
  );
}
