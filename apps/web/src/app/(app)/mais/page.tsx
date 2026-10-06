"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { MORE_ITEMS } from "@/components/shell";

const HINT: Record<string, string> = {
  "/projetos": "Contexto e tarefas por projeto",
  "/treinos": "Jiu-Jitsu, academia e cota semanal",
  "/atividade": "O que o Claude e você alteraram, com desfazer",
  "/config": "Preferências, conexão com o Claude e segurança",
};

export default function MorePage() {
  return (
    <div>
      <header className="pb-3 pt-2"><h1 className="text-[28px] font-semibold tracking-tight">Mais</h1></header>
      <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
        {MORE_ITEMS.map((i) => (
          <li key={i.href}>
            <Link href={i.href} className="flex items-center gap-4 px-4 py-4 transition hover:bg-surface2/60">
              <span className="grid size-10 place-items-center rounded-xl bg-surface2"><i.icon className="size-5" /></span>
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{i.label}</span>
                <span className="block truncate text-sm text-muted">{HINT[i.href]}</span>
              </span>
              <ChevronRight className="size-4 text-faint" />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
