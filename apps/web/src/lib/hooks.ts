"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";
import { useToast } from "@/components/providers";
import { api } from "./api";
import { nowIn } from "./time";
import type {
  AvailableTopic, Context, OpBatch, Preferences, Project, Routine, Schedule, StudyOverview, Task, Topic,
} from "./types";

const POLL = 45_000; // Claude edits from outside the app; keep the open screen fresh

export const useContextQ = () =>
  useQuery({ queryKey: ["context"], queryFn: () => api.get<Context>("/context"), refetchInterval: POLL });

export const useSchedule = (start: string, end: string, free = true) =>
  useQuery({
    queryKey: ["schedule", start, end, free],
    queryFn: () => api.get<Schedule>("/schedule", { start, end, free }),
    refetchInterval: POLL,
    placeholderData: (prev) => prev,
  });

export const useTasks = (params: Record<string, unknown>) =>
  useQuery({
    queryKey: ["tasks", params],
    queryFn: () => api.get<{ tasks: Task[]; count: number; truncated: boolean }>("/tasks", params),
    placeholderData: (prev) => prev,
    refetchInterval: POLL,
  });

export const useProjects = (status?: string) =>
  useQuery({ queryKey: ["projects", status], queryFn: () => api.get<{ projects: Project[] }>("/projects", { status }) });

export const useProject = (id: string | null) =>
  useQuery({
    queryKey: ["project", id],
    enabled: !!id,
    queryFn: () => api.get<{ project: Project }>(`/projects/${id}`),
  });

export const useRoutines = () =>
  useQuery({
    queryKey: ["routines"],
    queryFn: () => api.get<{ routines: Routine[] }>("/routines", { include_inactive: true, sessions: 3 }),
  });

export const useRoadmap = () =>
  useQuery({
    queryKey: ["study", "roadmap"],
    queryFn: () => api.get<{ overview: StudyOverview; roots: Topic[] }>("/study", { depth: 8 }),
    refetchInterval: POLL,
  });

export const useAvailable = () =>
  useQuery({
    queryKey: ["study", "available"],
    queryFn: () => api.get<{ overview: StudyOverview; available: AvailableTopic[] }>("/study", { only_available: true }),
    refetchInterval: POLL,
  });

export const useTopic = (id: string | null) =>
  useQuery({
    queryKey: ["study", "topic", id],
    enabled: !!id,
    queryFn: () => api.get<{ topic: Topic }>("/study", { topic_id: id, depth: 0 }),
  });

export const usePrefs = () => useQuery({ queryKey: ["prefs"], queryFn: () => api.get<Preferences>("/preferences") });

export const useOps = (actor?: string) =>
  useQuery({
    queryKey: ["ops", actor],
    queryFn: () => api.get<{ batches: OpBatch[] }>("/operations", { actor, limit: 60, since_hours: 24 * 14 }),
    refetchInterval: POLL,
  });

/** Runs a mutation, refreshes every query, and reports errors as toasts. Resolves to undefined on failure. */
export function useAct() {
  const qc = useQueryClient();
  const toast = useToast();
  return useCallback(
    async <T,>(fn: () => Promise<T>, okMessage?: string): Promise<T | undefined> => {
      try {
        const r = await fn();
        await qc.invalidateQueries();
        if (okMessage) toast.show(okMessage);
        return r;
      } catch (e) {
        toast.error(e);
        return undefined;
      }
    },
    [qc, toast],
  );
}

/** Wall-clock "now" in the user's timezone, refreshed every 30s. */
export function useNow(tz: string) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 30_000);
    return () => clearInterval(id);
  }, []);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  return useMemo(() => nowIn(tz), [tz, tick]);
}

/** Hydration-safe media query for the desktop layout. */
export function useIsDesktop() {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia("(min-width: 1024px)");
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia("(min-width: 1024px)").matches,
    () => false,
  );
}
