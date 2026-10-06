export type Actor = "manual" | "claude" | "system";
export type Mobility = "fixed" | "flexible";
export type Category =
  | "meeting" | "appointment" | "work" | "study" | "training" | "meal" | "personal" | "rest" | "other";
export type EntryStatus = "planned" | "done" | "skipped" | "cancelled";
export type TaskStatus = "inbox" | "todo" | "doing" | "done" | "cancelled";
export type Priority = "low" | "medium" | "high" | "urgent";
export type StudyStatus = "not_started" | "in_progress" | "done" | "paused" | "skipped";

export interface Link { id: string; name: string }

export interface Entry {
  id: string;
  title: string;
  mobility: Mobility;
  category: Category;
  start: string; // local ISO with offset: wall-clock = chars 0..16
  end: string;
  minutes: number;
  all_day?: boolean;
  status: EntryStatus;
  skip_reason?: string;
  location?: string;
  notes?: string;
  version: number;
  created_by: Actor;
  recurring?: boolean;
  rrule?: string;
  occurrence_start?: string;
  series_id?: string;
  task?: Link;
  study_topic?: Link;
  routine?: Link;
  project?: Link;
  overlaps_with?: string[];
}

export interface FreeWindow { start: string; end: string; minutes: number }

export interface DayPlan {
  id: string;
  summary?: string;
  rationale?: string;
  status: string;
  version: number;
  updated_by?: Actor;
}

export interface Day {
  date: string;
  weekday: string;
  is_today: boolean;
  plan: DayPlan | null;
  all_day: Entry[];
  entries: Entry[];
  free_windows?: FreeWindow[];
  stats: {
    planned_minutes: number;
    done_minutes: number;
    entries: number;
    entries_done: number;
    entries_skipped: number;
    free_minutes?: number;
  };
}

export interface Schedule { range: { start: string; end: string }; tz: string; days: Day[] }

export interface Task {
  id: string;
  title: string;
  status: TaskStatus;
  priority: Priority;
  due_date?: string;
  do_date?: string;
  estimated_minutes?: number;
  project_id?: string;
  project_name?: string;
  parent_id?: string;
  category?: string;
  overdue?: boolean;
  scheduled?: { id: string; start: string; end: string }[];
  description?: string;
  notes?: string;
  completed_at?: string;
  created_at?: string;
  version: number;
  created_by: Actor;
}

export interface Project {
  id: string;
  name: string;
  status: "active" | "paused" | "done" | "archived";
  area: "work" | "personal" | "study" | "health";
  description?: string;
  color?: string;
  version: number;
  open_tasks?: number;
  done_tasks?: number;
  overdue_tasks?: number;
  last_activity?: string;
  created_by?: Actor;
  tasks?: Task[];
}

export interface Exercise {
  key?: string;
  name: string;
  sets?: number;
  reps?: string;
  load?: string;
  rest_seconds?: number;
  notes?: string;
}
export interface Workout { key?: string; name: string; exercises: Exercise[] }

export interface SessionExercise extends Exercise {
  key: string;
  done: boolean | null;
  actual?: string;
  note?: string;
  extra?: boolean;
}
export interface WorkoutSession {
  id: string;
  routine_id: string;
  routine_name?: string;
  date: string;
  workout_key?: string;
  workout_name: string;
  entry_id?: string;
  finished: boolean;
  summary: { total: number; done: number; not_done: number; pending: number };
  effort?: number;
  duration_minutes?: number;
  notes?: string;
  version: number;
  exercises?: SessionExercise[];
}

export interface Routine {
  id: string;
  kind: "training";
  name: string;
  description?: string;
  target_per_week: number;
  duration_minutes: number;
  preferred_days?: number[];
  preferred_start?: string;
  preferred_end?: string;
  notes?: string;
  active: boolean;
  version: number;
  done_this_week?: number;
  planned_this_week?: number;
  workouts?: Workout[];
  recent_sessions?: WorkoutSession[];
}

export interface Resource { title: string; url?: string; kind?: string; done?: boolean }

export interface Topic {
  id: string;
  name: string;
  kind: "area" | "topic";
  status: StudyStatus;
  progress: number;
  difficulty?: number;
  estimated_minutes?: number;
  minutes_spent?: number;
  last_studied?: string;
  prerequisites?: string[];
  blocked_by?: string[];
  leaves?: string;
  children?: Topic[];
  children_count?: number;
  version: number;
  // detail only
  parent_id?: string;
  path?: string;
  description?: string;
  notes?: string;
  resources?: Resource[];
  required_by?: string[];
  recent_sessions?: { id: string; date: string; minutes: number; notes?: string }[];
}

export interface AvailableTopic {
  id: string;
  path: string;
  status: StudyStatus;
  progress: number;
  difficulty?: number;
  estimated_minutes?: number;
  minutes_spent?: number;
  last_studied?: string;
  version: number;
}

export interface StudyOverview { topics: number; done: number; in_progress: number; progress: number }

export interface Meal { name: string; start: string; end: string }
export interface Preferences {
  timezone: string;
  version: number;
  wake_time: string;
  sleep_time: string;
  work_days: number[];
  work_start: string;
  work_end: string;
  meals: Meal[];
  planning_rules: string[];
  context_notes: string;
  min_free_window_minutes: number;
}

export interface Context {
  now: string;
  today: string;
  weekday: string;
  timezone: string;
  preferences: Preferences;
  tasks: { open: number; inbox: number; due_next_3_days: number; overdue: Task[]; for_today: Task[] };
  projects: { id: string; name: string; area: string; open_tasks?: number; overdue_tasks?: number }[];
  routines: Routine[];
  study: { overview: StudyOverview; available_next: AvailableTopic[] };
}

export interface OpBatch {
  batch_id: string;
  ts: string;
  actor: Actor;
  channel: string;
  tool: string;
  result: "ok" | "rejected";
  undone_by?: string;
  count: number;
  changes: { action: string; entity?: string; summary: string; error?: string }[];
}

export interface Warning { code: string; message: string }
