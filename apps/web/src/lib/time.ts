// Server timestamps are ISO strings already expressed in the user's timezone, so the wall-clock
// time is simply a slice of the string. This file avoids any browser-timezone arithmetic.

export const hm = (iso: string) => iso.slice(11, 16);
export const ymd = (iso: string) => iso.slice(0, 10);
export const minutesOf = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
export const pad = (n: number) => String(n).padStart(2, "0");
export const fromMinutes = (m: number) => `${pad(Math.floor(m / 60) % 24)}:${pad(m % 60)}`;

export function nowIn(tz: string): { date: string; hm: string; minutes: number } {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date());
  const g = (t: string) => parts.find((p) => p.type === t)?.value ?? "00";
  const time = `${g("hour")}:${g("minute")}`;
  return { date: `${g("year")}-${g("month")}-${g("day")}`, hm: time, minutes: minutesOf(time) };
}

const toUTC = (d: string) => {
  const [y, m, day] = d.split("-").map(Number);
  return Date.UTC(y, m - 1, day);
};
export const addDays = (d: string, n: number) => new Date(toUTC(d) + n * 86400000).toISOString().slice(0, 10);
export const weekStart = (d: string) => {
  const wd = (new Date(toUTC(d)).getUTCDay() + 6) % 7; // Monday = 0
  return addDays(d, -wd);
};
export const monthStart = (d: string) => `${d.slice(0, 7)}-01`;
export const addMonths = (d: string, n: number) => {
  const [y, m] = d.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1 + n, 1));
  return t.toISOString().slice(0, 10);
};
export const monthEnd = (d: string) => addDays(addMonths(monthStart(d), 1), -1);
export const diffDays = (a: string, b: string) => Math.round((toUTC(a) - toUTC(b)) / 86400000);

const fmt = (d: string, opts: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat("pt-BR", { timeZone: "UTC", ...opts }).format(new Date(toUTC(d)));
export const fmtLong = (d: string) => fmt(d, { weekday: "long", day: "numeric", month: "long" });
export const fmtShort = (d: string) => fmt(d, { day: "numeric", month: "short" }).replace(".", "");
export const fmtWeekday = (d: string) => fmt(d, { weekday: "short" }).replace(".", "");
export const fmtDayNum = (d: string) => fmt(d, { day: "numeric" });
export const fmtMonthYear = (d: string) => fmt(d, { month: "long", year: "numeric" });

export function relDay(d: string, today: string): string {
  const n = diffDays(d, today);
  if (n === 0) return "Hoje";
  if (n === 1) return "Amanhã";
  if (n === -1) return "Ontem";
  if (n > 1 && n < 7) return fmt(d, { weekday: "long" });
  return fmtShort(d);
}

export function dur(mins: number): string {
  if (mins < 60) return `${mins}min`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m ? `${h}h${pad(m)}` : `${h}h`;
}

export const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
export const RRULE_DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];

export function greeting(h: number) {
  if (h < 5) return "Boa madrugada";
  if (h < 12) return "Bom dia";
  if (h < 18) return "Boa tarde";
  return "Boa noite";
}
