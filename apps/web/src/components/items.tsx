"use client";

import { AlertCircle, CalendarClock, Clock, Lock, Repeat } from "lucide-react";
import { catLabel } from "@/lib/entry";
import { dur, hm, relDay } from "@/lib/time";
import type { Entry, Task } from "@/lib/types";
import { Check, ClaudeBadge, Chip, cx } from "./ui";

const PRIORITY_TONE: Record<string, string> = { urgent: "var(--danger)", high: "var(--accent)" };

export function TaskRow({
  task, today, onOpen, onToggle, showProject = true,
}: { task: Task; today: string; onOpen: () => void; onToggle: () => void; showProject?: boolean }) {
  const done = task.status === "done";
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onOpen()}
      className="flex w-full items-start gap-3 rounded-2xl px-3 py-3 text-left transition hover:bg-surface2/60 active:bg-surface2"
    >
      <div className="pt-0.5">
        <Check checked={done} onChange={onToggle} label={done ? "Reabrir tarefa" : "Concluir tarefa"} tone={PRIORITY_TONE[task.priority]} />
      </div>
      <div className="min-w-0 flex-1">
        <p className={cx("text-[15px] leading-snug", done && "text-muted line-through")}>
          {task.title}
          {task.created_by === "claude" && <ClaudeBadge className="ml-1.5 align-[-1px]" />}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted">
          {task.status === "inbox" && <Chip tone="accent">inbox</Chip>}
          {showProject && task.project_name && <span>{task.project_name}</span>}
          {task.due_date && (
            <span className={cx("inline-flex items-center gap-1", task.overdue && "font-medium text-danger")}>
              {task.overdue && <AlertCircle className="size-3" />}
              prazo {relDay(task.due_date, today).toLowerCase()}
            </span>
          )}
          {task.do_date && task.do_date !== today && !done && <span>fazer {relDay(task.do_date, today).toLowerCase()}</span>}
          {task.estimated_minutes && (
            <span className="inline-flex items-center gap-1"><Clock className="size-3" />{dur(task.estimated_minutes)}</span>
          )}
          {task.scheduled?.length ? (
            <span className="inline-flex items-center gap-1 text-text/70"><CalendarClock className="size-3" />{hm(task.scheduled[0].start)}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function EntryMeta({ e }: { e: Entry }) {
  const link = e.task?.name ?? e.study_topic?.name ?? e.routine?.name ?? e.project?.name;
  return (
    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs opacity-75">
      <span>{catLabel(e.category)}</span>
      <span>{dur(e.minutes)}</span>
      {link && <span className="max-w-[14rem] truncate">· {link}</span>}
      {e.location && <span className="truncate">· {e.location}</span>}
    </div>
  );
}

export function EntryIcons({ e }: { e: Entry }) {
  return (
    <span className="inline-flex items-center gap-1 align-middle opacity-70">
      {e.mobility === "fixed" && <Lock className="size-3" aria-label="Fixo" />}
      {e.recurring || e.series_id ? <Repeat className="size-3" aria-label="Recorrente" /> : null}
      {e.created_by === "claude" && <ClaudeBadge />}
    </span>
  );
}
