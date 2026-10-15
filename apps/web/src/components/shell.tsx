"use client";

import {
  Activity, BookOpen, CalendarRange, Dumbbell, FolderKanban, ListChecks, MoreHorizontal, PanelLeftClose, PanelLeftOpen,
  Plus, Settings, Sun,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore, type ReactNode } from "react";
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

function Brand({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="relative grid size-8 shrink-0 place-items-center rounded-[10px] bg-ink">
        <span className="size-3.5 rounded-full border-2 border-inkfg" />
        <span className="absolute right-1 top-1 size-1.5 rounded-full bg-accent" />
      </span>
      {!compact && <span className="whitespace-nowrap text-[17px] font-semibold tracking-tight">Personal OS</span>}
    </div>
  );
}

// Desktop sidebar: expanded (labels) or collapsed (thin, icons only). The choice is remembered on this device.
const NAV_KEY = "pos-nav-collapsed";
const NAV_EVENT = "pos-nav-collapsed-change";

function useNavCollapsed(): [boolean, (v: boolean) => void] {
  const collapsed = useSyncExternalStore(
    (cb) => {
      window.addEventListener(NAV_EVENT, cb);
      window.addEventListener("storage", cb);
      return () => {
        window.removeEventListener(NAV_EVENT, cb);
        window.removeEventListener("storage", cb);
      };
    },
    () => {
      try {
        return localStorage.getItem(NAV_KEY) === "1";
      } catch {
        return false;
      }
    },
    () => false,
  );
  const set = (v: boolean) => {
    try {
      localStorage.setItem(NAV_KEY, v ? "1" : "0");
    } catch { /* ignore */ }
    window.dispatchEvent(new Event(NAV_EVENT));
  };
  return [collapsed, set];
}

function Fab() {
  const path = usePathname();
  const sheets = useSheets();
  const ctx = useContextQ();
  let onClick: (() => void) | null = null;
  let label = "Adicionar";
  if (path === "/" || path === "/agenda") onClick = () => sheets.quickAdd(ctx.data?.today);
  else if (path === "/tarefas") { onClick = () => sheets.task(null); label = "Nova tarefa"; }
  else if (path === "/estudos") { onClick = () => sheets.topic(null); label = "Nova trilha"; }
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
  const [collapsed, setCollapsed] = useNavCollapsed();
  return (
    <div className={cx("min-h-dvh transition-[padding] duration-200", collapsed ? "lg:pl-14" : "lg:pl-64")}>
      <aside
        className={cx(
          "fixed inset-y-0 left-0 z-20 hidden flex-col overflow-hidden border-r border-line bg-bg py-5 transition-[width] duration-200 lg:flex",
          collapsed ? "w-14 items-center px-2" : "w-64 px-4",
        )}
      >
        <Link href="/" className={cx("mb-7", collapsed ? "" : "px-2")} aria-label="Personal OS" title="Personal OS">
          <Brand compact={collapsed} />
        </Link>
        <nav className={cx("flex flex-col gap-1", collapsed && "items-center")}>
          {[...MAIN, ...MORE].map((i, idx) => (
            <div key={i.href} className={collapsed ? "flex flex-col items-center" : undefined}>
              {idx === MAIN.length && <div className={cx("my-3 h-px bg-line", collapsed ? "w-6" : "w-full")} />}
              <Link
                href={i.href}
                title={collapsed ? i.label : undefined}
                aria-label={i.label}
                aria-current={active(path, i.href) ? "page" : undefined}
                className={cx(
                  "flex items-center rounded-xl text-[15px] font-medium transition",
                  collapsed ? "size-10 justify-center" : "gap-3 px-3 py-2.5",
                  active(path, i.href) ? "bg-surface2 text-text" : "text-muted hover:bg-surface2/60 hover:text-text",
                )}
              >
                <i.icon className="size-[18px] shrink-0" />
                {!collapsed && <span className="whitespace-nowrap">{i.label}</span>}
              </Link>
            </div>
          ))}
        </nav>
        <div className={cx("mt-auto flex w-full items-center", collapsed ? "justify-center" : "justify-between gap-2 px-3")}>
          {!collapsed && <p className="text-xs text-faint">O Claude opera este app via MCP.</p>}
          <button
            onClick={() => setCollapsed(!collapsed)}
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
            title={collapsed ? "Expandir menu" : "Recolher menu"}
            aria-expanded={!collapsed}
            className="grid size-9 shrink-0 place-items-center rounded-lg text-faint transition hover:bg-surface2 hover:text-text"
          >
            {collapsed ? <PanelLeftOpen className="size-[18px]" /> : <PanelLeftClose className="size-[18px]" />}
          </button>
        </div>
      </aside>

      <main
        className={cx("mx-auto px-4 lg:px-8", wide ? "max-w-screen-2xl" : "max-w-2xl")}
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

