import { api } from "./api";
import type { Entry, EntryStatus, Task } from "./types";

/** PATCH an entry. A virtual occurrence of a recurring series is addressed by series id + occurrence_start. */
export function patchEntry(e: Entry, body: Record<string, unknown>) {
  const virtual = e.recurring && !e.series_id;
  return api.patch(`/calendar/${e.id}`, {
    ...body,
    version: e.version,
    ...(virtual ? { scope: "this", occurrence_start: e.occurrence_start ?? e.start } : {}),
  });
}

export const setEntryStatus = (e: Entry, status: EntryStatus, skip_reason?: string) =>
  patchEntry(e, { status, skip_reason: status === "skipped" ? skip_reason || null : null });

export const toggleTask = (t: Task) =>
  api.patch(`/tasks/${t.id}`, { status: t.status === "done" ? "todo" : "done", version: t.version });
