import type { NextRequest } from "next/server";

// Server-side proxy: the browser only ever talks to this origin; /api/* is forwarded to the FastAPI service.
// API_URL is read at request time, so changing it never needs a rebuild.
export const dynamic = "force-dynamic";

const HOP_BY_HOP = ["connection", "keep-alive", "transfer-encoding", "upgrade", "te", "trailer", "proxy-authorization"];

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const base = (process.env.API_URL || "http://localhost:8000").replace(/\/$/, "");
  const { path } = await ctx.params;
  const target = `${base}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;

  const headers = new Headers(req.headers);
  for (const h of [...HOP_BY_HOP, "host", "content-length", "accept-encoding"]) headers.delete(h);
  headers.set("x-forwarded-host", req.headers.get("host") ?? "");
  headers.set("x-forwarded-proto", req.nextUrl.protocol.replace(":", ""));

  const hasBody = !["GET", "HEAD"].includes(req.method);
  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? await req.arrayBuffer() : undefined,
      redirect: "manual",
      cache: "no-store",
    });
  } catch {
    return Response.json(
      { ok: false, error: { code: "UPSTREAM_UNREACHABLE", message: "Não foi possível falar com o servidor (API_URL correta?)" } },
      { status: 502 },
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
