"use client";

import { BookOpen, CalendarPlus, ChevronDown, ChevronRight, Lock, Play, Plus } from "lucide-react";
import { useState } from "react";
import { useSheets } from "@/components/sheets/host";
import { Bar, Button, Chip, Empty, Segmented, Spinner, cx } from "@/components/ui";
import { useAvailable, useRoadmap } from "@/lib/hooks";
import { STATUS_LABEL } from "@/lib/study";
import { dur, fmtShort } from "@/lib/time";
import type { Topic } from "@/lib/types";

function Node({ t, depth, open, toggle, onOpen, onAdd, blockedNames }: {
  t: Topic; depth: number; open: Set<string>; toggle: (id: string) => void;
  onOpen: (t: Topic) => void; onAdd: (t: Topic) => void; blockedNames: Map<string, string>;
}) {
  const kids = t.children ?? [];
  const isOpen = open.has(t.id);
  const leaf = kids.length === 0 && !t.children_count;
  const blocked = !!t.blocked_by?.length && t.status !== "done";
  return (
    <li>
      <div
        className={cx("group flex items-center gap-1 rounded-xl pr-1 transition hover:bg-surface2/70", depth === 0 && "mt-3")}
        style={{ paddingLeft: depth * 14 }}
      >
        <button
          onClick={() => (leaf ? onOpen(t) : toggle(t.id))}
          className="grid size-9 shrink-0 place-items-center text-muted"
          aria-label={leaf ? "Abrir" : isOpen ? "Recolher" : "Expandir"}
        >
          {leaf ? <span className={cx("size-2 rounded-full", t.status === "done" ? "bg-ok" : t.status === "in_progress" ? "bg-accent" : "bg-faint")} /> : (isOpen ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />)}
        </button>
        <button onClick={() => onOpen(t)} className="min-w-0 flex-1 py-2 text-left">
          <div className="flex items-center gap-2">
            <span className={cx("truncate", depth === 0 ? "text-[17px] font-semibold" : "text-[15px]", t.status === "done" && "text-muted line-through")}>{t.name}</span>
            {blocked && <Lock className="size-3 shrink-0 text-faint" aria-label="Bloqueado por pré-requisito" />}
          </div>
          {(!leaf || t.progress > 0) && (
            <div className="mt-1.5 flex items-center gap-2">
              <Bar value={t.progress} tone={t.status === "done" ? "ok" : "ink"} className="max-w-40 flex-1" />
              <span className="text-xs tabular-nums text-muted">{t.leaves ?? `${t.progress}%`}</span>
            </div>
          )}
          {blocked && <p className="mt-0.5 text-xs text-faint">Requer: {t.blocked_by!.map((b) => blockedNames.get(b) ?? b).join(", ")}</p>}
        </button>
        <button onClick={() => onAdd(t)} aria-label="Adicionar subtópico" className="grid size-9 place-items-center rounded-lg text-faint opacity-60 hover:bg-surface2 hover:text-text group-hover:opacity-100">
          <Plus className="size-4" />
        </button>
      </div>
      {isOpen && kids.length > 0 && (
        <ul>
          {kids.map((c) => <Node key={c.id} t={c} depth={depth + 1} open={open} toggle={toggle} onOpen={onOpen} onAdd={onAdd} blockedNames={blockedNames} />)}
        </ul>
      )}
    </li>
  );
}

function names(roots: Topic[], m = new Map<string, string>()) {
  for (const t of roots) { m.set(t.id, t.name); if (t.children) names(t.children, m); }
  return m;
}

export default function StudyPage() {
  const sheets = useSheets();
  const [tab, setTab] = useState<"roadmap" | "available">("roadmap");
  const road = useRoadmap();
  const avail = useAvailable();
  const [open, setOpen] = useState<Set<string>>(() => {
    try {
      const raw = typeof window === "undefined" ? null : localStorage.getItem("pos-study-open");
      return new Set<string>(raw ? JSON.parse(raw) : []);
    } catch {
      return new Set<string>();
    }
  });
  const toggle = (id: string) =>
    setOpen((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      try { localStorage.setItem("pos-study-open", JSON.stringify([...n])); } catch { /* ignore */ }
      return n;
    });

  const ov = road.data?.overview;
  const nameMap = names(road.data?.roots ?? []);

  return (
    <div>
      <header className="pb-3 pt-2">
        <h1 className="text-[28px] font-semibold tracking-tight">Estudos</h1>
        <p className="text-sm text-muted">O que aprender. Quando estudar é decidido na agenda.</p>
      </header>

      {ov && ov.topics > 0 && (
        <div className="mb-4 rounded-2xl border border-line bg-surface p-4">
          <div className="flex items-end justify-between">
            <div>
              <p className="text-3xl font-semibold tabular-nums">{ov.progress}%</p>
              <p className="text-sm text-muted">{ov.done} de {ov.topics} tópicos concluídos</p>
            </div>
            <Chip tone="accent">{ov.in_progress} em andamento</Chip>
          </div>
          <Bar value={ov.progress} className="mt-3 h-2" tone="accent" />
        </div>
      )}

      <Segmented value={tab} onChange={setTab} options={[{ value: "roadmap", label: "Roadmap" }, { value: "available", label: `Disponíveis${avail.data ? ` · ${avail.data.available.length}` : ""}` }]} />

      {tab === "roadmap" ? (
        road.isLoading ? (
          <div className="grid place-items-center py-16"><Spinner /></div>
        ) : !road.data?.roots.length ? (
          <Empty
            icon={<BookOpen className="size-5" />}
            title="Seu roadmap está vazio"
            hint="Crie áreas e tópicos manualmente, ou peça ao Claude: “monte meu roadmap de backend com Python e FastAPI”."
            action={<Button onClick={() => sheets.topic(null)}><Plus className="size-4" />Nova área</Button>}
          />
        ) : (
          <ul className="mt-1">
            {road.data.roots.map((r) => (
              <Node key={r.id} t={r} depth={0} open={open} toggle={toggle} onOpen={(t) => sheets.topic(t.id)} onAdd={(t) => sheets.topic(null, t.id)} blockedNames={nameMap} />
            ))}
          </ul>
        )
      ) : avail.isLoading ? (
        <div className="grid place-items-center py-16"><Spinner /></div>
      ) : !avail.data?.available.length ? (
        <Empty icon={<BookOpen className="size-5" />} title="Nada disponível agora" hint="Tópicos aparecem aqui quando os pré-requisitos estão concluídos." />
      ) : (
        <ul className="mt-3 space-y-2">
          {avail.data.available.map((a) => (
            <li key={a.id} className="rounded-2xl border border-line bg-surface p-3.5">
              <button onClick={() => sheets.topic(a.id)} className="block w-full text-left">
                <p className="text-xs text-muted">{a.path.split(" › ").slice(0, -1).join(" › ")}</p>
                <p className="mt-0.5 font-medium">{a.path.split(" › ").at(-1)}</p>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                  <Chip tone={a.status === "in_progress" ? "accent" : "muted"}>{STATUS_LABEL[a.status]}</Chip>
                  {a.progress > 0 && <span>{a.progress}%</span>}
                  {a.minutes_spent ? <span>{dur(a.minutes_spent)} estudados</span> : null}
                  {a.last_studied && <span>último {fmtShort(a.last_studied)}</span>}
                  {a.estimated_minutes ? <span>~{dur(a.estimated_minutes)}</span> : null}
                </div>
              </button>
              <div className="mt-3 flex gap-2">
                <Button size="sm" variant="soft" onClick={() => sheets.logStudy(a.id)}><Play className="size-3.5" />Registrar estudo</Button>
                <Button size="sm" variant="ghost" onClick={() => sheets.entry(null, { mobility: "flexible", category: "study", study_topic_id: a.id, title: a.path.split(" › ").at(-1) })}>
                  <CalendarPlus className="size-3.5" />Agendar
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
