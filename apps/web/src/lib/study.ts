import type { Topic } from "./types";

export type FlatTopic = { id: string; name: string; depth: number; path: string; leaf: boolean; topic: Topic };

export function flattenTopics(roots: Topic[] | undefined): FlatTopic[] {
  const out: FlatTopic[] = [];
  const walk = (ts: Topic[], depth: number, prefix: string) => {
    for (const t of ts) {
      const path = prefix ? `${prefix} › ${t.name}` : t.name;
      const leaf = !t.children && !t.children_count;
      out.push({ id: t.id, name: t.name, depth, path, leaf, topic: t });
      if (t.children) walk(t.children, depth + 1, path);
    }
  };
  walk(roots ?? [], 0, "");
  return out;
}

export const STATUS_LABEL: Record<string, string> = {
  not_started: "Não iniciado",
  in_progress: "Em andamento",
  done: "Concluído",
  paused: "Pausado",
  skipped: "Ignorado",
};
