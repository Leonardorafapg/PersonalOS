"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { ApiError, setWarningHandler } from "@/lib/api";
import type { Warning } from "@/lib/types";

type ToastItem = { id: number; kind: "ok" | "error" | "warn"; text: string; hint?: string };
type ToastApi = {
  show: (text: string) => void;
  error: (e: unknown) => void;
  warnings: (w: Warning[]) => void;
};

const ToastCtx = createContext<ToastApi>({ show() {}, error() {}, warnings() {} });
export const useToast = () => useContext(ToastCtx);

function Toasts({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);
  const push = useCallback((t: Omit<ToastItem, "id">, ms = 4200) => {
    const id = ++seq.current;
    setItems((s) => [...s.slice(-3), { ...t, id }]);
    setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), ms);
  }, []);
  const api = useMemo<ToastApi>(
    () => ({
      show: (text) => push({ kind: "ok", text }, 2600),
      error: (e) => {
        const err = e instanceof ApiError ? e : null;
        push({ kind: "error", text: err?.message || (e instanceof Error ? e.message : "Algo deu errado"), hint: err?.hint }, 6000);
      },
      warnings: (w) => w.slice(0, 2).forEach((x) => push({ kind: "warn", text: x.message }, 6000)),
    }),
    [push],
  );
  useEffect(() => setWarningHandler(api.warnings), [api]);
  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-0 z-[60] flex flex-col items-center gap-2 px-4 bottom-[calc(84px+var(--safe-bottom))] lg:bottom-6"
        aria-live="polite"
      >
        {items.map((t) => (
          <div
            key={t.id}
            className="anim-sheet pointer-events-auto flex max-w-md items-start gap-2.5 rounded-2xl border border-line bg-surface px-4 py-3 text-sm shadow-xl"
          >
            {t.kind === "ok" && <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok" />}
            {t.kind === "error" && <XCircle className="mt-0.5 size-4 shrink-0 text-danger" />}
            {t.kind === "warn" && <AlertTriangle className="mt-0.5 size-4 shrink-0 text-accent" />}
            <div>
              <p>{t.text}</p>
              {t.hint && <p className="mt-0.5 text-xs text-muted">{t.hint}</p>}
            </div>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: true, retry: 1 } },
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <Toasts>{children}</Toasts>
    </QueryClientProvider>
  );
}
