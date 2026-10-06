"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { Entry, Project, Routine, Task } from "@/lib/types";
import { EntrySheet, type EntryDefaults } from "./EntrySheet";
import { LogStudySheet, ProjectSheet, QuickAddSheet, RoutineSheet } from "./SmallSheets";
import { TaskSheet, type TaskDefaults } from "./TaskSheet";
import { TopicSheet } from "./TopicSheet";
import { WorkoutSheet, type WorkoutTarget } from "./WorkoutSheet";

type Open =
  | { k: "task"; task: Task | null; defaults?: TaskDefaults }
  | { k: "entry"; entry: Entry | null; defaults?: EntryDefaults }
  | { k: "topic"; id: string | null; parentId?: string }
  | { k: "log"; topicId: string; entryId?: string }
  | { k: "project"; project: Project | null }
  | { k: "routine"; routine: Routine | null }
  | { k: "workout"; target: WorkoutTarget }
  | { k: "quick"; date?: string }
  | null;

export type Sheets = {
  task: (task?: Task | null, defaults?: TaskDefaults) => void;
  entry: (entry?: Entry | null, defaults?: EntryDefaults) => void;
  topic: (id?: string | null, parentId?: string) => void;
  logStudy: (topicId: string, entryId?: string) => void;
  project: (p?: Project | null) => void;
  routine: (r?: Routine | null) => void;
  workout: (target: WorkoutTarget) => void;
  quickAdd: (date?: string) => void;
};

const Ctx = createContext<Sheets | null>(null);
export const useSheets = () => {
  const c = useContext(Ctx);
  if (!c) throw new Error("SheetHost missing");
  return c;
};

export function SheetHost({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState<Open>(null);
  const [stamp, setStamp] = useState(0);
  const show = useCallback((o: Open) => { setStamp((n) => n + 1); setOpen(o); }, []);
  const close = useCallback(() => setOpen(null), []);

  const api = useMemo<Sheets>(
    () => ({
      task: (task = null, defaults) => show({ k: "task", task, defaults }),
      entry: (entry = null, defaults) => show({ k: "entry", entry, defaults }),
      topic: (id = null, parentId) => show({ k: "topic", id, parentId }),
      logStudy: (topicId, entryId) => show({ k: "log", topicId, entryId }),
      project: (project = null) => show({ k: "project", project }),
      routine: (routine = null) => show({ k: "routine", routine }),
      workout: (target) => show({ k: "workout", target }),
      quickAdd: (date) => show({ k: "quick", date }),
    }),
    [show],
  );

  return (
    <Ctx.Provider value={api}>
      {children}
      {open?.k === "task" && <TaskSheet key={stamp} task={open.task} defaults={open.defaults} onClose={close} />}
      {open?.k === "entry" && <EntrySheet key={stamp} entry={open.entry} defaults={open.defaults} onClose={close} />}
      {open?.k === "topic" && (
        <TopicSheet
          key={stamp} topicId={open.id} parentId={open.parentId} onClose={close}
          onLog={(id) => api.logStudy(id)}
          onSchedule={(id) => api.entry(null, { mobility: "flexible", category: "study", study_topic_id: id })}
        />
      )}
      {open?.k === "log" && <LogStudySheet key={stamp} topicId={open.topicId} entryId={open.entryId} onClose={close} />}
      {open?.k === "project" && <ProjectSheet key={stamp} project={open.project} onClose={close} />}
      {open?.k === "workout" && <WorkoutSheet key={stamp} target={open.target} onClose={close} />}
      {open?.k === "routine" && <RoutineSheet key={stamp} routine={open.routine} onClose={close} />}
      {open?.k === "quick" && (
        <QuickAddSheet
          key={stamp}
          onClose={close}
          onPick={(k) => {
            const date = open.date;
            if (k === "task") api.task(null, date ? { do_date: date } : undefined);
            else api.entry(null, { mobility: k === "fixed" ? "fixed" : "flexible", date, category: k === "fixed" ? "meeting" : "work" });
          }}
        />
      )}
    </Ctx.Provider>
  );
}
