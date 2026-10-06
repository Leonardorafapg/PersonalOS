import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Sessions live in an httpOnly cookie issued by the API. No cookie -> go to /login.
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = request.cookies.has("pos_session");
  if (!hasSession && pathname !== "/login") {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }
  if (hasSession && pathname === "/login") {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next|manifest.webmanifest|sw.js|offline.html|icons|favicon.ico|.*\\.(?:png|svg|jpg|ico|webp)$).*)"],
};
