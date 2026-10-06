"use client";

import { ExternalLink, Plus, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useAct, useRoadmap, useTopic } from "@/lib/hooks";
import { STATUS_LABEL, flattenTopics } from "@/lib/study";
import { dur, fmtShort } from "@/lib/time";
import type { Resource, StudyStatus, Topic } from "@/lib/types";
import { Bar, Button, Chip, Field, Segmented, Sheet, Spinner, cx, inputCls } from "../ui";

export function TopicSheet({
  topicId,
  parentId,
  onClose,
  onLog,
  onSchedule,
}: {
  topicId: string | null;
  parentId?: string;
  onClose: () => void;
  onLog: (id: string) => void;
  onSchedule: (id: string) => void;
}) {
  const detail = useTopic(topicId);
  if (topicId && !detail.data)
    return (
      <Sheet open onClose={onClose} title="Tópico">
        <div className="grid place-items-center py-16"><Spinner /></div>
      </Sheet>
    );
  return (
    <TopicForm
      key={topicId ?? "new"}
      topic={detail.data?.topic ?? null}
      parentId={parentId}
      onClose={onClose}
      onLog={onLog}
      onSchedule={onSchedule}
    />
  );
}

function TopicForm({
  topic, parentId, onClose, onLog, onSchedule,
}: { topic: Topic | null; parentId?: string; onClose: () => void; onLog: (id: string) => void; onSchedule: (id: string) => void }) {
  const act = useAct();
  const roadmap = useRoadmap();
  const flat = useMemo(() => flattenTopics(roadmap.data?.roots), [roadmap.data]);
  const hasChildren = !!topic && (!!topic.children?.length || !!topic.children_count || !!topic.leaves);
  const [f, setF] = useState(() => ({
    name: topic?.name ?? "",
    kind: (topic?.kind ?? (parentId ? "topic" : "area")) as "area" | "topic",
    parent_id: topic?.parent_id ?? parentId ?? "",
    description: topic?.description ?? "",
    status: (topic?.status ?? "not_started") as StudyStatus,
    progress: topic?.progress ?? 0,
    difficulty: topic?.difficulty ?? 0,
    estimated_minutes: topic?.estimated_minutes ? String(topic.estimated_minutes) : "",
    notes: topic?.notes ?? "",
    resources: (topic?.resources ?? []) as Resource[],
    prerequisites: (topic?.prerequisites ?? []) as string[],
  }));
  const [delStep, setDelStep] = useState(false);
  const [search, setSearch] = useState("");
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((s) => ({ ...s, [k]: v }));

  const candidates = flat.filter((t) => t.id !== topic?.id && t.path.toLowerCase().includes(search.toLowerCase())).slice(0, 40);

  const save = async () => {
    const body: Record<string, unknown> = {
      name: f.name.trim(),
      kind: f.kind,
      parent_id: f.parent_id || null,
      description: f.description || null,
      difficulty: f.difficulty || null,
      estimated_minutes: f.estimated_minutes ? Number(f.estimated_minutes) : null,
      notes: f.notes || null,
      resources: f.resources.filter((r) => r.title.trim()),
      prerequisites: f.prerequisites,
    };
    if (!hasChildren) {
      body.status = f.status;
      body.progress = f.progress;
    }
    const r = await act(
      () => (topic ? api.patch(`/study/topics/${topic.id}`, { ...body, version: topic.version }) : api.post("/study/topics", body)),
      topic ? "Tópico atualizado" : "Tópico criado",
    );
    if (r) onClose();
  };

  const remove = async () => {
    if (!topic) return;
    const r = await act(() => api.del(`/study-topics/${topic.id}`), "Tópico excluído");
    if (r) onClose();
  };

  const setProgress = (p: number) =>
    setF((s) => ({ ...s, progress: p, status: p >= 100 ? "done" : s.status === "done" ? "in_progress" : p > 0 && s.status === "not_started" ? "in_progress" : s.status }));

  return (
    <Sheet
      open
      onClose={onClose}
      wide
      title={topic ? topic.name : "Novo tópico"}
      footer={
        delStep && topic ? (
          <div className="space-y-2">
            <p className="text-center text-sm text-muted">Excluir este tópico{hasChildren ? " e todos os subtópicos" : ""}?</p>
            <div className="flex gap-2">
              <Button variant="soft" onClick={() => setDelStep(false)}>Cancelar</Button>
              <Button variant="danger" className="flex-1" onClick={remove}>Excluir</Button>
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            {topic && <Button variant="danger" onClick={() => setDelStep(true)} aria-label="Excluir"><Trash2 className="size-4" /></Button>}
            <Button className="flex-1" onClick={save} disabled={!f.name.trim()}>{topic ? "Salvar" : "Criar tópico"}</Button>
          </div>
        )
      }
    >
      <div className="space-y-4 pt-1">
        {topic?.path && <p className="text-xs text-muted">{topic.path}</p>}
        <input
          autoFocus={!topic}
          className="w-full bg-transparent text-xl font-semibold tracking-tight outline-none placeholder:text-faint"
          placeholder="Nome do tópico (ex.: Async / Await)"
          value={f.name}
          onChange={(e) => set("name", e.target.value)}
        />

        {topic && (
          <div className="flex flex-wrap items-center gap-2">
            <Chip tone={topic.status === "done" ? "ok" : topic.status === "in_progress" ? "accent" : "muted"}>{STATUS_LABEL[topic.status]}</Chip>
            {!!topic.minutes_spent && <Chip>{dur(topic.minutes_spent)} estudados</Chip>}
            {topic.last_studied && <Chip>último: {fmtShort(topic.last_studied)}</Chip>}
            {topic.blocked_by?.length ? <Chip tone="danger">bloqueado por pré-requisito</Chip> : null}
          </div>
        )}
        {topic && (
          <div className="flex gap-2">
            <Button variant="soft" size="sm" onClick={() => onLog(topic.id)}>Registrar estudo</Button>
            {!hasChildren && <Button variant="soft" size="sm" onClick={() => onSchedule(topic.id)}>Agendar bloco</Button>}
          </div>
        )}

        {hasChildren ? (
          <div className="rounded-xl bg-surface2 px-4 py-3 text-sm text-muted">
            O progresso deste tópico é calculado a partir dos subtópicos ({topic?.leaves}).
            <Bar value={topic?.progress ?? 0} className="mt-2" />
          </div>
        ) : (
          <>
            <Field label="Status">
              <select className={inputCls} value={f.status} onChange={(e) => { const v = e.target.value as StudyStatus; setF((s) => ({ ...s, status: v, progress: v === "done" ? 100 : v === "not_started" ? 0 : s.progress })); }}>
                {Object.entries(STATUS_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
            <Field label={`Progresso · ${f.progress}%`}>
              <input type="range" min={0} max={100} step={5} value={f.progress} onChange={(e) => setProgress(Number(e.target.value))} className="w-full accent-[var(--ink)]" />
            </Field>
          </>
        )}

        <Field label="Descrição">
          <textarea className={inputCls} rows={2} value={f.description} onChange={(e) => set("description", e.target.value)} />
        </Field>

        <div className="grid grid-cols-2 gap-3">
          <Field label="Tipo">
            <Segmented value={f.kind} onChange={(v) => set("kind", v)} options={[{ value: "area", label: "Área" }, { value: "topic", label: "Tópico" }]} />
          </Field>
          <Field label="Tempo estimado (min)">
            <input type="number" min={1} inputMode="numeric" className={inputCls} value={f.estimated_minutes} onChange={(e) => set("estimated_minutes", e.target.value)} />
          </Field>
        </div>

        <Field label="Dificuldade">
          <div className="flex gap-1.5">
            {[1, 2, 3, 4, 5].map((n) => (
              <button key={n} type="button" onClick={() => set("difficulty", f.difficulty === n ? 0 : n)}
                className={cx("h-9 flex-1 rounded-lg text-sm font-medium transition", f.difficulty >= n ? "bg-ink text-inkfg" : "bg-surface2 text-muted")}>
                {n}
              </button>
            ))}
          </div>
        </Field>

        <Field label="Dentro de">
          <select className={inputCls} value={f.parent_id} onChange={(e) => set("parent_id", e.target.value)}>
            <option value="">Raiz (sem pai)</option>
            {flat.filter((t) => t.id !== topic?.id).map((t) => (
              <option key={t.id} value={t.id}>{"  ".repeat(t.depth)}{t.name}</option>
            ))}
          </select>
        </Field>

        <Field label="Pré-requisitos" hint="Tópicos que precisam estar concluídos antes">
          {f.prerequisites.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {f.prerequisites.map((id) => {
                const t = flat.find((x) => x.id === id);
                return (
                  <button key={id} type="button" onClick={() => set("prerequisites", f.prerequisites.filter((x) => x !== id))}
                    className="inline-flex items-center gap-1 rounded-full bg-surface2 py-1 pl-3 pr-2 text-sm">
                    {t?.name ?? id} <X className="size-3.5 text-muted" />
                  </button>
                );
              })}
            </div>
          )}
          <input className={inputCls} placeholder="Buscar tópico…" value={search} onChange={(e) => setSearch(e.target.value)} />
          {search && (
            <div className="mt-1 max-h-44 overflow-y-auto rounded-xl border border-line">
              {candidates.map((t) => (
                <button key={t.id} type="button" disabled={f.prerequisites.includes(t.id)}
                  onClick={() => { set("prerequisites", [...f.prerequisites, t.id]); setSearch(""); }}
                  className="block w-full truncate px-3 py-2 text-left text-sm hover:bg-surface2 disabled:opacity-40">
                  {t.path}
                </button>
              ))}
              {!candidates.length && <p className="px-3 py-2 text-sm text-muted">Nada encontrado</p>}
            </div>
          )}
        </Field>

        <Field label="Recursos">
          <div className="space-y-2">
            {f.resources.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <input className={inputCls} placeholder="Título" value={r.title} onChange={(e) => set("resources", f.resources.map((x, j) => (j === i ? { ...x, title: e.target.value } : x)))} />
                <input className={inputCls} placeholder="https://…" value={r.url ?? ""} onChange={(e) => set("resources", f.resources.map((x, j) => (j === i ? { ...x, url: e.target.value || undefined } : x)))} />
                {r.url && <a href={r.url} target="_blank" rel="noreferrer" aria-label="Abrir" className="p-2 text-muted"><ExternalLink className="size-4" /></a>}
                <button type="button" aria-label="Remover" onClick={() => set("resources", f.resources.filter((_, j) => j !== i))} className="p-2 text-muted"><X className="size-4" /></button>
              </div>
            ))}
            <Button variant="ghost" size="sm" onClick={() => set("resources", [...f.resources, { title: "" }])}><Plus className="size-4" /> Adicionar recurso</Button>
          </div>
        </Field>

        <Field label="Observações">
          <textarea className={inputCls} rows={2} value={f.notes} onChange={(e) => set("notes", e.target.value)} />
        </Field>

        {topic?.recent_sessions?.length ? (
          <div>
            <p className="mb-1.5 text-[13px] font-medium text-muted">Sessões recentes</p>
            <ul className="divide-y divide-line rounded-xl border border-line">
              {topic.recent_sessions.map((s) => (
                <li key={s.id} className="flex items-center justify-between px-3 py-2 text-sm">
                  <span>{fmtShort(s.date)}{s.notes ? ` · ${s.notes}` : ""}</span>
                  <span className="tabular-nums text-muted">{dur(s.minutes)}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </Sheet>
  );
}
