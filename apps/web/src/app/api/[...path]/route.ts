import type { NextRequest } from "next/server";

// Server-side proxy: the browser only ever talks to this origin; /api/* is forwarded to the FastAPI service.
// API_URL is read at request time, so changing it never needs a rebuild.
export const dynamic = "force-dynamic";

const HOP_BY_HOP = ["connection", "keep-alive", "transfer-encoding", "upgrade", "te", "trailer", "proxy-authorization"];

/** Accepts "host", "http://host" or "https://host/"; public hosts are always called over https. */
function apiBase(): string {
  let b = (process.env.API_URL || "http://localhost:8000").trim();
  if (!/^https?:\/\//i.test(b)) b = `https://${b}`;
  const local = /^http:\/\/(localhost|127\.0\.0\.1|\[::1\]|[^/]*\.internal)(:|\/|$)/i.test(b);
  if (/^http:\/\//i.test(b) && !local) b = `https://${b.slice(7)}`;
  return b.replace(/\/+$/, "");
}

function fail(status: number, code: string, message: string) {
  return Response.json({ ok: false, error: { code, message } }, { status });
}

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const base = apiBase();
  const { path } = await ctx.params;
  const target = `${base}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  const headers = new Headers(req.headers);
  for (const h of [...HOP_BY_HOP, "host", "content-length", "accept-encoding"]) headers.delete(h);
  headers.set("x-forwarded-host", req.headers.get("host") ?? "");
  headers.set("x-forwarded-proto", req.nextUrl.protocol.replace(":", ""));

  const hasBody = !["GET", "HEAD"].includes(req.method);
  const body = hasBody ? await req.arrayBuffer() : undefined;

  let upstream: Response;
  try {
    // Redirects are followed here (307/308 keep method and body) so they never leak to the browser.
    upstream = await fetch(target, { method: req.method, headers, body, redirect: "follow", cache: "no-store" });
  } catch {
    return fail(502, "UPSTREAM_UNREACHABLE", `Não foi possível falar com a API em ${new URL(base).host}. Confira a variável API_URL.`);
  }

  // A non-JSON error (e.g. the platform's own 502 page) means the API service itself is down.
  const type = upstream.headers.get("content-type") ?? "";
  if (upstream.status >= 500 && !type.includes("json")) {
    return fail(
      502,
      "UPSTREAM_DOWN",
      `A API (${new URL(base).host}) respondeu ${upstream.status}. O serviço não está rodando: veja os logs de deploy dele no Railway.`,
    );
  }

  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    const k = key.toLowerCase();
    if (HOP_BY_HOP.includes(k) || k === "content-encoding" || k === "content-length" || k === "set-cookie") return;
    out.set(key, value);
  });
  for (const cookie of upstream.headers.getSetCookie()) out.append("set-cookie", cookie);
  return new Response(upstream.status === 204 || upstream.status === 304 ? null : upstream.body, {
    status: upstream.status,
    headers: out,
  });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE, forward as OPTIONS };
