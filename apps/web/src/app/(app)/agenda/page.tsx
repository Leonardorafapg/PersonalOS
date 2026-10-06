"use client";

import { ChevronLeft, ChevronRight, Lock, Repeat } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useSheets } from "@/components/sheets/host";
import { ClaudeBadge, Segmented, Spinner, cx } from "@/components/ui";
import { useContextQ, useIsDesktop, useNow, useSchedule } from "@/lib/hooks";
import {
  WEEKDAYS, addDays, addMonths, dur, fmtDayNum, fmtMonthYear, fmtShort, fmtWeekday, fromMinutes, hm, minutesOf,
  monthEnd, monthStart, nowIn, weekStart, ymd,
} from "@/lib/time";
import type { Day, Entry } from "@/lib/types";

const GUTTER = 44;

type Placed = { e: Entry; s: number; en: number; lane: number; lanes: number };

function place(entries: Entry[], date: string): Placed[] {
  const items = entries
    .filter((e) => !e.all_day && e.status !== "cancelled")
    .map((e) => ({
      e,
      s: ymd(e.start) < date ? 0 : minutesOf(hm(e.start)),
      en: ymd(e.end) > ymd(e.start) ? 1440 : Math.max(minutesOf(hm(e.end)), minutesOf(hm(e.start)) + 15),
    }))
    .sort((a, b) => a.s - b.s || b.en - a.en);
  const out: Placed[] = [];
  let cluster: Placed[] = [];
  let clusterEnd = -1;
  let laneEnds: number[] = [];
  const flush = () => {
    cluster.forEach((p) => (p.lanes = laneEnds.length));
    out.push(...cluster);
    cluster = [];
    laneEnds = [];
  };
  for (const it of items) {
    if (cluster.length && it.s >= clusterEnd) flush();
    let lane = laneEnds.findIndex((end) => end <= it.s);
    if (lane === -1) { lane = laneEnds.length; laneEnds.push(it.en); } else laneEnds[lane] = it.en;
    cluster.push({ ...it, lane, lanes: 1 });
    clusterEnd = Math.max(clusterEnd, it.en);
  }
  flush();
  return out;
}

function DayColumn({
  day, gridStart, gridEnd, hour, nowMin, compact, onOpen, onCreate,
}: {
  day: Day; gridStart: number; gridEnd: number; hour: number; nowMin: number | null; compact: boolean;
  onOpen: (e: Entry) => void; onCreate: (date: string, start: string, end: string, flexible: boolean) => void;
}) {
  const placed = useMemo(() => place(day.entries, day.date), [day]);
  const top = (m: number) => ((m - gridStart * 60) / 60) * hour;
  const height = (gridEnd - gridStart) * hour;

  return (
    <div
      className={cx("relative flex-1 border-l border-line", day.is_today && "bg-accent/[.035]")}
      style={{ height, minWidth: 0 }}
      onClick={(ev) => {
        const rect = ev.currentTarget.getBoundingClientRect();
        const mins = Math.round(((ev.clientY - rect.top) / hour) * 4) * 15 + gridStart * 60;
        const s = Math.min(Math.max(mins, gridStart * 60), 23 * 60);
        onCreate(day.date, fromMinutes(s), fromMinutes(Math.min(s + 60, 23 * 60 + 59)), false);
      }}
    >
      {Array.from({ length: gridEnd - gridStart }, (_, i) => (
        <div key={i} className="pointer-events-none absolute inset-x-0 border-t border-line/70" style={{ top: i * hour }} />
      ))}
      {day.free_windows?.map((w) => {
        const s = minutesOf(hm(w.start));
        const en = ymd(w.end) > ymd(w.start) ? 1440 : minutesOf(hm(w.end));
        if (en <= gridStart * 60 || s >= gridEnd * 60) return null;
        return (
          <button
            key={w.start}
            aria-label={`Livre ${hm(w.start)} a ${hm(w.end)}`}
            onClick={(ev) => { ev.stopPropagation(); onCreate(day.date, hm(w.start), fromMinutes(Math.min(s + Math.min(60, w.minutes), 23 * 60 + 59)), true); }}
            className="absolute inset-x-0 cursor-copy bg-[var(--free)] transition hover:bg-[var(--free)] hover:brightness-95"
            style={{ top: top(Math.max(s, gridStart * 60)), height: ((Math.min(en, gridEnd * 60) - Math.max(s, gridStart * 60)) / 60) * hour }}
          />
        );
      })}
      {placed.map(({ e, s, en, lane, lanes }) => {
        const h = Math.max(((Math.min(en, gridEnd * 60) - Math.max(s, gridStart * 60)) / 60) * hour, 22);
        const roomy = h >= 44;
        return (
          <button
            key={`${e.id}-${e.start}`}
            onClick={(ev) => { ev.stopPropagation(); onOpen(e); }}
            className={cx("entry absolute overflow-hidden text-left transition hover:z-10 hover:shadow-md", compact ? "px-1.5 py-1" : "px-2.5 py-1.5")}
            data-cat={e.category} data-mob={e.mobility} data-status={e.status}
            style={{
              top: top(Math.max(s, gridStart * 60)), height: h - 2,
              left: `calc(${(lane / lanes) * 100}% + 2px)`, width: `calc(${100 / lanes}% - 4px)`,
              borderRadius: compact ? 8 : 10,
            }}
          >
            <div className={cx("flex items-start gap-1 font-medium leading-tight", compact ? "text-[11px]" : "text-[13px]")}>
              <span className="min-w-0 flex-1 truncate">{e.title}</span>
              {e.mobility === "fixed" && !compact && <Lock className="mt-0.5 size-3 shrink-0 opacity-60" />}
              {(e.recurring || e.series_id) && !compact && <Repeat className="mt-0.5 size-3 shrink-0 opacity-60" />}
              {e.created_by === "claude" && !compact && <ClaudeBadge className="mt-0.5 shrink-0" />}
            </div>
            {roomy && (
              <div className={cx("opacity-70", compact ? "text-[10px]" : "text-xs")}>
                {hm(e.start)}–{hm(e.end)}{!compact && ` · ${dur(e.minutes)}`}
              </div>
            )}
          </button>
        );
      })}
      {nowMin !== null && nowMin >= gridStart * 60 && nowMin <= gridEnd * 60 && (
        <div className="pointer-events-none absolute inset-x-0 z-20 flex items-center" style={{ top: top(nowMin) }}>
          <span className="-ml-1 size-2 rounded-full bg-accent" />
          <span className="h-px flex-1 bg-accent" />
        </div>
      )}
    </div>
  );
}

const MAX_PILLS = 3;

function MonthGrid({ days, month, onPick }: { days: Day[]; month: string; onPick: (date: string) => void }) {
  const weeks: Day[][] = [];
  for (let i = 0; i < days.length; i += 7) weeks.push(days.slice(i, i + 7));
  return (
    <div>
      <div className="grid grid-cols-7 border-b border-line">
        {WEEKDAYS.map((w) => (
          <div key={w} className="py-2 text-center text-[11px] font-medium uppercase tracking-wide text-muted">{w}</div>
        ))}
      </div>
      {weeks.map((wk, wi) => (
        <div key={wi} className="grid grid-cols-7">
          {wk.map((d) => {
            const items = [...d.all_day, ...d.entries.filter((e) => e.status !== "cancelled")];
            const inMonth = d.date.startsWith(month);
            const shown = items.slice(0, MAX_PILLS);
            const rest = items.length - shown.length;
            return (
              <button
                key={d.date}
                onClick={() => onPick(d.date)}
                aria-label={`${fmtShort(d.date)}: ${items.length} itens`}
                className={cx(
                  "flex min-h-[76px] min-w-0 flex-col items-stretch gap-1 border-l border-t border-line p-1 text-left transition hover:bg-surface2/60 sm:min-h-[112px] sm:p-1.5",
                  wi === 0 && "border-t-0", d.is_today && "bg-accent/[.05]", !inMonth && "opacity-45",
                )}
              >
                <span className={cx("grid size-6 place-items-center self-end rounded-full text-[13px] font-semibold tabular-nums sm:self-start", d.is_today && "bg-accent text-accentfg")}>
                  {fmtDayNum(d.date)}
                </span>
                <span className="hidden min-w-0 flex-col gap-0.5 sm:flex">
                  {shown.map((e) => (
                    <span
                      key={`${e.id}-${e.start}`}
                      className="entry truncate px-1.5 py-0.5 text-[11px] font-medium leading-tight"
                      data-cat={e.category} data-mob={e.mobility} data-status={e.status}
                      style={{ borderRadius: 6 }}
                    >
                      {!e.all_day && <span className="mr-1 opacity-60">{hm(e.start)}</span>}{e.title}
                    </span>
                  ))}
                  {rest > 0 && <span className="px-1 text-[11px] text-muted">+{rest} mais</span>}
                </span>
                <span className="flex flex-wrap items-center justify-center gap-0.5 sm:hidden">
                  {items.slice(0, 6).map((e) => (
                    <span
                      key={`${e.id}-${e.start}`}
                      className={cx("size-1.5 rounded-full", e.mobility === "flexible" && "border border-current bg-transparent")}
                      style={{ background: e.mobility === "fixed" ? `var(--c-${e.category})` : "transparent", color: `var(--c-${e.category})` }}
                    />
                  ))}
                </span>
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export default function AgendaPage() {
  const sheets = useSheets();
  const ctx = useContextQ();
  const tz = ctx.data?.timezone ?? "America/Sao_Paulo";
  const today = ctx.data?.today ?? nowIn(tz).date;
  const desktop = useIsDesktop();
  const [viewPick, setView] = useState<"day" | "week" | "month" | null>(null);
  const view = viewPick ?? (desktop ? "week" : "day");
  const [anchor, setAnchor] = useState<string | null>(null);
  const cur = anchor ?? today;
  const nowMin = useNow(tz).minutes;

  const start = view === "day" ? cur : view === "week" ? weekStart(cur) : weekStart(monthStart(cur));
  const end = view === "day" ? cur : view === "week" ? addDays(start, 6) : addDays(weekStart(monthEnd(cur)), 6);
  const sched = useSchedule(start, end, view !== "month");
  const days = useMemo(() => sched.data?.days ?? [], [sched.data]);

  // visible hour range: wake-ish .. midnight, extended to fit early entries
  const gridStart = useMemo(() => {
    const wake = ctx.data ? Number(ctx.data.preferences.wake_time.slice(0, 2)) : 7;
    let g = Math.max(0, Math.min(6, wake - 1));
    for (const d of days) for (const e of d.entries) if (!e.all_day && ymd(e.start) === d.date) g = Math.min(g, Math.floor(minutesOf(hm(e.start)) / 60));
    return g;
  }, [days, ctx.data]);
  const gridEnd = 24;
  const hour = view === "day" ? 60 : 52;

  const scroller = useRef<HTMLDivElement>(null);
  const scrolledKey = useRef("");
  useEffect(() => {
    const key = `${view}-${start}`;
    if (!scroller.current || !sched.data || scrolledKey.current === key) return;
    scrolledKey.current = key;
    const showsToday = days.some((d) => d.is_today);
    const target = showsToday ? Math.max(nowMin - 90, gridStart * 60) : Math.max(8 * 60 - 30, gridStart * 60);
    scroller.current.scrollTop = ((target - gridStart * 60) / 60) * hour;
  }, [sched.data, view, start, days, nowMin, gridStart, hour]);

  const go = (dir: -1 | 1) => setAnchor(view === "month" ? addMonths(cur, dir) : addDays(cur, dir * (view === "day" ? 1 : 7)));
  const create = (date: string, s: string, e: string, flexible: boolean) =>
    sheets.entry(null, { date, start: s, end: e, mobility: flexible ? "flexible" : "fixed", category: flexible ? "work" : "other" });
  const title =
    view === "day" ? `${fmtWeekday(cur)}, ${fmtShort(cur)}` : view === "week" ? `${fmtShort(start)} – ${fmtShort(end)}` : fmtMonthYear(cur);
  const allDay = days.flatMap((d) => d.all_day.map((e) => ({ e, date: d.date })));

  return (
    <div>
      <header className="flex flex-wrap items-center justify-between gap-3 pb-3 pt-2">
        <div>
          <h1 className="text-[26px] font-semibold first-letter:uppercase leading-tight tracking-tight">{title}</h1>
          {view !== "month" && <p className="text-sm first-letter:uppercase text-muted">{fmtMonthYear(cur)}</p>}
        </div>
        <div className="flex items-center gap-2">
          <div className="w-56"><Segmented value={view} onChange={setView} options={[{ value: "day", label: "Dia" }, { value: "week", label: "Semana" }, { value: "month", label: "Mês" }]} /></div>
          <div className="flex items-center rounded-xl bg-surface2 p-1">
            <button aria-label="Anterior" onClick={() => go(-1)} className="grid size-8 place-items-center rounded-lg hover:bg-surface"><ChevronLeft className="size-4" /></button>
            <button onClick={() => setAnchor(null)} className="px-2.5 text-sm font-medium">Hoje</button>
            <button aria-label="Próximo" onClick={() => go(1)} className="grid size-8 place-items-center rounded-lg hover:bg-surface"><ChevronRight className="size-4" /></button>
          </div>
        </div>
      </header>

      {sched.isLoading ? (
        <div className="grid place-items-center py-24"><Spinner /></div>
      ) : view === "month" ? (
        <div className="overflow-hidden rounded-2xl border border-line bg-surface">
          <MonthGrid days={days} month={cur.slice(0, 7)} onPick={(d) => { setAnchor(d); setView("day"); }} />
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-line bg-surface">
          <div className="overflow-x-auto">
            <div className={cx(view === "week" && "min-w-[780px]")}>
              {view === "week" && (
                <div className="flex border-b border-line">
                  <div style={{ width: GUTTER }} className="shrink-0" />
                  {days.map((d) => (
                    <button key={d.date} onClick={() => { setAnchor(d.date); setView("day"); }} className="flex-1 border-l border-line py-2 text-center">
                      <div className="text-[11px] font-medium uppercase tracking-wide text-muted">{fmtWeekday(d.date)}</div>
                      <div className={cx("mx-auto mt-0.5 grid size-8 place-items-center rounded-full text-[15px] font-semibold", d.is_today && "bg-accent text-accentfg")}>{fmtDayNum(d.date)}</div>
                    </button>
                  ))}
                </div>
              )}
              {allDay.length > 0 && (
                <div className="flex border-b border-line">
                  <div style={{ width: GUTTER }} className="shrink-0 py-1.5 pr-1 text-right text-[10px] text-faint">dia todo</div>
                  {days.map((d) => (
                    <div key={d.date} className="min-w-0 flex-1 space-y-1 border-l border-line p-1">
                      {d.all_day.map((e) => (
                        <button key={e.id} onClick={() => sheets.entry(e)} className="entry block w-full truncate px-2 py-0.5 text-left text-xs font-medium" data-cat={e.category} data-mob={e.mobility}>{e.title}</button>
                      ))}
                    </div>
                  ))}
                </div>
              )}
              <div ref={scroller} className="max-h-[calc(100dvh-300px)] min-h-[420px] overflow-y-auto lg:max-h-[calc(100dvh-220px)]">
                <div className="flex">
                  <div style={{ width: GUTTER }} className="relative shrink-0" aria-hidden>
                    {Array.from({ length: gridEnd - gridStart }, (_, i) => (
                      <div key={i} className="absolute right-1.5 -translate-y-1/2 text-[10px] tabular-nums text-faint" style={{ top: i * hour }}>
                        {i === 0 ? "" : `${String(gridStart + i).padStart(2, "0")}:00`}
                      </div>
                    ))}
                    <div style={{ height: (gridEnd - gridStart) * hour }} />
                  </div>
                  {days.map((d) => (
                    <DayColumn
                      key={d.date} day={d} gridStart={gridStart} gridEnd={gridEnd} hour={hour}
                      nowMin={d.is_today ? nowMin : null} compact={view === "week"}
                      onOpen={(e) => sheets.entry(e)} onCreate={create}
                    />
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {view === "day" && days[0] && (
        <div className="mt-4 space-y-2 px-1 text-sm text-muted">
          {days[0].plan?.summary && <p><span className="font-medium text-text">Plano:</span> {days[0].plan.summary}</p>}
          {days[0].plan?.rationale && <p className="leading-relaxed">{days[0].plan.rationale}</p>}
          <p>
            {days[0].stats.entries} itens · {dur(days[0].stats.planned_minutes)} planejadas
            {days[0].stats.free_minutes !== undefined && ` · ${dur(days[0].stats.free_minutes)} livres`}
          </p>
          <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-faint">
            <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-4 rounded-[4px] border border-line bg-surface2 shadow-[inset_3px_0_0_var(--c-other)]" />Fixo</span>
            <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-4 rounded-[4px] border-[1.5px] border-dashed border-[var(--c-other)]" />Flexível (o Claude pode mover)</span>
            <span className="inline-flex items-center gap-1.5"><span className="inline-block h-3 w-4 rounded-[4px] bg-[var(--free)]" />Livre · toque para planejar</span>
          </p>
        </div>
      )}
    </div>
  );
}
