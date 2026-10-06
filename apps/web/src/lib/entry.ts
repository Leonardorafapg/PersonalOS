import type { Category } from "./types";
import { RRULE_DAYS } from "./time";

export const CATEGORIES: { value: Category; label: string }[] = [
  { value: "work", label: "Trabalho" },
  { value: "study", label: "Estudo" },
  { value: "training", label: "Treino" },
  { value: "meeting", label: "Reunião" },
  { value: "appointment", label: "Compromisso" },
  { value: "meal", label: "Refeição" },
  { value: "personal", label: "Pessoal" },
  { value: "rest", label: "Descanso" },
  { value: "other", label: "Outro" },
];
export const catLabel = (c: string) => CATEGORIES.find((x) => x.value === c)?.label ?? c;

export type Recurrence = { kind: "none" | "daily" | "weekdays" | "weekly" | "monthly" | "custom"; days: number[]; raw: string };

export function buildRRule(r: Recurrence): string | null {
  switch (r.kind) {
    case "none": return null;
    case "daily": return "FREQ=DAILY";
    case "weekdays": return "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR";
    case "weekly": return `FREQ=WEEKLY;BYDAY=${(r.days.length ? r.days : [0]).map((d) => RRULE_DAYS[d]).join(",")}`;
    case "monthly": return "FREQ=MONTHLY";
    case "custom": return r.raw.trim() || null;
  }
}

export function parseRRule(rule?: string | null): Recurrence {
  if (!rule) return { kind: "none", days: [], raw: "" };
  const u = rule.toUpperCase();
  if (u === "FREQ=DAILY") return { kind: "daily", days: [], raw: rule };
  if (u === "FREQ=MONTHLY") return { kind: "monthly", days: [], raw: rule };
  const m = u.match(/^FREQ=WEEKLY;BYDAY=([A-Z,]+)$/);
  if (m) {
    const days = m[1].split(",").map((d) => RRULE_DAYS.indexOf(d)).filter((i) => i >= 0);
    if (days.join() === "0,1,2,3,4") return { kind: "weekdays", days, raw: rule };
    return { kind: "weekly", days, raw: rule };
  }
  return { kind: "custom", days: [], raw: rule };
}
