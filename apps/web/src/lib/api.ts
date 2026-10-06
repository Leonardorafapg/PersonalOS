import type { Warning } from "./types";

export class ApiError extends Error {
  code: string;
  hint?: string;
  conflicts?: { id: string; title: string; start: string; end: string }[];
  status: number;
  constructor(status: number, e: { code?: string; message?: string; hint?: string; conflicts?: ApiError["conflicts"] }) {
    super(e.message || "Erro inesperado");
    this.status = status;
    this.code = e.code || "ERROR";
    this.hint = e.hint;
    this.conflicts = e.conflicts;
  }
}

type WarnHandler = (w: Warning[]) => void;
let onWarnings: WarnHandler = () => {};
export function setWarningHandler(fn: WarnHandler) {
  onWarnings = fn;
}

async function request<T>(method: string, path: string, body?: unknown, params?: Record<string, unknown>): Promise<T> {
  let url = `/api${path}`;
  if (params) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === "") continue;
      if (Array.isArray(v)) v.forEach((x) => qs.append(k, String(x)));
      else qs.append(k, String(v));
    }
    const s = qs.toString();
    if (s) url += `?${s}`;
  }
  const res = await fetch(url, {
    method,
    credentials: "same-origin",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let env: { ok: boolean; data?: T; error?: ConstructorParameters<typeof ApiError>[1]; warnings?: Warning[] } | null = null;
  try {
    env = await res.json();
  } catch {
    /* non-JSON error page */
  }
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/login")) {
    window.location.replace("/login");
    throw new ApiError(401, { code: "UNAUTHORIZED", message: "Sessão expirada" });
  }
  if (!res.ok || !env || env.ok === false) {
    throw new ApiError(res.status, env?.error || { message: `Erro ${res.status}` });
  }
  if (env.warnings?.length) onWarnings(env.warnings);
  return env.data as T;
}

export const api = {
  get: <T>(path: string, params?: Record<string, unknown>) => request<T>("GET", path, undefined, params),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string, params?: Record<string, unknown>) => request<T>("DELETE", path, undefined, params),
};
