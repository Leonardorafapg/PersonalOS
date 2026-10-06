"use client";

import {
  Activity, BookOpen, CalendarRange, Dumbbell, FolderKanban, ListChecks, MoreHorizontal, Plus, Settings, Sun,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useContextQ } from "@/lib/hooks";
import { SheetHost, useSheets } from "./sheets/host";
import { cx } from "./ui";

const MAIN = [
  { href: "/", label: "Hoje", icon: Sun },
  { href: "/agenda", label: "Agenda", icon: CalendarRange },
  { href: "/tarefas", label: "Tarefas", icon: ListChecks },
  { href: "/estudos", label: "Estudos", icon: BookOpen },
];
const MORE = [
  { href: "/projetos", label: "Projetos", icon: FolderKanban },
  { href: "/treinos", label: "Treinos", icon: Dumbbell },
  { href: "/atividade", label: "Atividade", icon: Activity },
  { href: "/config", label: "Configurações", icon: Settings },
];
export const MORE_ITEMS = MORE;

const active = (path: string, href: string) => (href === "/" ? path === "/" : path === href || path.startsWith(href + "/"));

function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <span className="grid size-8 place-items-center rounded-[10px] bg-ink">
        <span className="size-3.5 rounded-full border-2 border-inkfg" />
        <span className="absolute size-1.5 translate-x-[7px] -translate-y-[7px] rounded-full bg-accent" />
      </span>
      <span className="text-[17px] font-semibold tracking-tight">Personal OS</span>
    </div>
  );
}

function Fab() {
  const path = usePathname();
  const sheets = useSheets();
  const ctx = useContextQ();
  let onClick: (() => void) | null = null;
  let label = "Adicionar";
  if (path === "/" || path === "/agenda") onClick = () => sheets.quickAdd(ctx.data?.today);
  else if (path === "/tarefas") { onClick = () => sheets.task(null); label = "Nova tarefa"; }
  else if (path === "/estudos") { onClick = () => sheets.topic(null); label = "Novo tópico"; }
  else if (path === "/projetos") { onClick = () => sheets.project(null); label = "Novo projeto"; }
  else if (path === "/treinos") { onClick = () => sheets.routine(null); label = "Novo treino"; }
  if (!onClick) return null;
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className="fixed right-4 z-30 grid size-14 place-items-center rounded-full bg-accent text-accentfg shadow-lg shadow-accent/30 transition active:scale-95 bottom-[calc(76px+var(--safe-bottom))] lg:bottom-8 lg:right-8"
    >
      <Plus className="size-6" strokeWidth={2.4} />
    </button>
  );
}

function Shell({ children }: { children: ReactNode }) {
  const path = usePathname();
  const wide = path.startsWith("/agenda");
  const moreActive = MORE.some((m) => active(path, m.href)) || path === "/mais";
  return (
    <div className="min-h-dvh lg:pl-64">
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r border-line bg-bg px-4 py-6 lg:flex">
        <Link href="/" className="mb-8 px-2"><Brand /></Link>
        <nav className="flex flex-col gap-1">
          {[...MAIN, ...MORE].map((i, idx) => (
            <div key={i.href}>
              {idx === MAIN.length && <div className="my-3 h-px bg-line" />}
              <Link
                href={i.href}
                className={cx(
                  "flex items-center gap-3 rounded-xl px-3 py-2.5 text-[15px] font-medium transition",
                  active(path, i.href) ? "bg-surface2 text-text" : "text-muted hover:bg-surface2/60 hover:text-text",
                )}
              >
                <i.icon className="size-[18px]" /> {i.label}
              </Link>
            </div>
          ))}
        </nav>
        <p className="mt-auto px-3 text-xs text-faint">O Claude opera este app via MCP.</p>
      </aside>

      <main
        className={cx("mx-auto px-4 lg:px-8", wide ? "max-w-6xl" : "max-w-2xl")}
        style={{ paddingTop: "max(16px, env(safe-area-inset-top))", paddingBottom: "calc(112px + var(--safe-bottom))" }}
      >
        {children}
      </main>

      <Fab />

      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-line bg-bg/85 backdrop-blur-xl lg:hidden"
        style={{ paddingBottom: "var(--safe-bottom)" }}
        aria-label="Navegação principal"
      >
        <div className="mx-auto grid max-w-md grid-cols-5">
          {MAIN.map((i) => (
            <Link key={i.href} href={i.href} className={cx("flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium", active(path, i.href) ? "text-text" : "text-faint")}>
              <i.icon className="size-[22px]" strokeWidth={active(path, i.href) ? 2.4 : 1.8} />
              {i.label}
            </Link>
          ))}
          <Link href="/mais" className={cx("flex flex-col items-center gap-0.5 py-2.5 text-[11px] font-medium", moreActive ? "text-text" : "text-faint")}>
            <MoreHorizontal className="size-[22px]" strokeWidth={moreActive ? 2.4 : 1.8} />
            Mais
          </Link>
        </div>
      </nav>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <SheetHost>
      <Shell>{children}</Shell>
    </SheetHost>
  );
}

