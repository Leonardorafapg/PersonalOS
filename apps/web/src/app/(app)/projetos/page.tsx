"use client";

import { ArrowLeft, FolderKanban, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { TaskRow } from "@/components/items";
import { useSheets } from "@/components/sheets/host";
import { Button, Chip, Empty, IconButton, Spinner } from "@/components/ui";
import { toggleTask } from "@/lib/actions";
import { useAct, useContextQ, useProject, useProjects } from "@/lib/hooks";
import { relDay } from "@/lib/time";

const AREA: Record<string, string> = { work: "Trabalho", personal: "Pessoal", study: "Estudo", health: "Saúde" };

function Detail({ id, onBack }: { id: string; onBack: () => void }) {
  const sheets = useSheets();
  const act = useAct();
  const ctx = useContextQ();
  const today = ctx.data?.today ?? "";
  const q = useProject(id);
  const p = q.data?.project;
  if (!p) return <div className="grid place-items-center py-24"><Spinner /></div>;
  const open = (p.tasks ?? []).filter((t) => t.status !== "done" && t.status !== "cancelled");
  return (
    <div>
      <header className="flex items-start gap-2 pb-3 pt-2">
        <IconButton label="Voltar" onClick={onBack} className="-ml-2"><ArrowLeft className="size-5" /></IconButton>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[26px] font-semibold tracking-tight">{p.name}</h1>
          <div className="mt-1 flex flex-wrap gap-2">
            <Chip>{AREA[p.area]}</Chip>
            {p.status !== "active" && <Chip tone="muted">{p.status}</Chip>}
            <Chip>{p.open_tasks ?? 0} abertas</Chip>
            {!!p.overdue_tasks && <Chip tone="danger">{p.overdue_tasks} atrasadas</Chip>}
            {p.last_activity && <Chip>atividade {relDay(p.last_activity.slice(0, 10), today).toLowerCase()}</Chip>}
          </div>
        </div>
        <IconButton label="Editar projeto" onClick={() => sheets.project(p)}><Pencil className="size-4" /></IconButton>
      </header>
      {p.description && <p className="mb-4 whitespace-pre-line rounded-2xl bg-surface2 p-4 text-sm leading-relaxed text-muted">{p.description}</p>}
      <div className="mb-2 flex items-center justify-between px-1">
        <h2 className="text-[13px] font-semibold uppercase tracking-wider text-muted">Tarefas</h2>
        <Button size="sm" variant="soft" onClick={() => sheets.task(null, { project_id: p.id })}><Plus className="size-4" />Nova</Button>
      </div>
      {open.length === 0 ? <Empty title="Sem tarefas abertas" /> : (
        <div className="-mx-1">
          {open.map((t) => <TaskRow key={t.id} task={t} today={today} showProject={false} onOpen={() => sheets.task(t)} onToggle={() => act(() => toggleTask(t))} />)}
        </div>
      )}
    </div>
  );
}

export default function ProjectsPage() {
  const sheets = useSheets();
  const q = useProjects();
  const [sel, setSel] = useState<string | null>(null);
  if (sel) return <Detail id={sel} onBack={() => setSel(null)} />;
  const list = q.data?.projects ?? [];
  return (
    <div>
      <header className="pb-3 pt-2"><h1 className="text-[28px] font-semibold tracking-tight">Projetos</h1></header>
      {q.isLoading ? <div className="grid place-items-center py-16"><Spinner /></div> : list.length === 0 ? (
        <Empty icon={<FolderKanban className="size-5" />} title="Nenhum projeto" hint="Projetos dão contexto às tarefas, para o Claude entender o que é importante." action={<Button onClick={() => sheets.project(null)}><Plus className="size-4" />Novo projeto</Button>} />
      ) : (
        <ul className="space-y-2">
          {list.map((p) => (
            <li key={p.id}>
              <button onClick={() => setSel(p.id)} className="w-full rounded-2xl border border-line bg-surface p-4 text-left transition hover:bg-surface2/50 active:scale-[.99]">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-[17px] font-semibold">{p.name}</p>
                  <Chip>{AREA[p.area]}</Chip>
                </div>
                {p.description && <p className="mt-1 line-clamp-2 text-sm text-muted">{p.description}</p>}
                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  <Chip>{p.open_tasks ?? 0} abertas</Chip>
                  {!!p.overdue_tasks && <Chip tone="danger">{p.overdue_tasks} atrasadas</Chip>}
                  {p.status !== "active" && <Chip tone="muted">{p.status}</Chip>}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
