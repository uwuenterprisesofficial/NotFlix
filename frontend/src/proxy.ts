import { type NextRequest, NextResponse } from "next/server";
import { backendUrl, isDesktop } from "@/lib/backend";

// Tells the backend which origin the browser uses, so a sign-in started in the desktop app
// returns there (the backend only accepts loopback origins for this).
const ORIGIN_HEADER = "x-notflix-origin";

/**
 * The browser only ever talks to this origin; /api/* is passed on to FastAPI, so the session
 * cookie is first-party and the OAuth callbacks can live at /api/auth/... (A proxy rather than
 * a rewrite in next.config: those are fixed at build time, and the backend is chosen at run
 * time.)
 */
export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const target = new URL(`${backendUrl()}${pathname.slice("/api".length)}${search}`);
  const headers = new Headers(request.headers);
  // The Host the browser used (nextUrl says "localhost" for 127.0.0.1, which has other cookies).
  // Elsewhere the header passes through: the desktop app may reach the backend through the web
  // app's /api.
  const host = request.headers.get("host");
  if (isDesktop() && host) headers.set(ORIGIN_HEADER, `http://${host}`);
  return NextResponse.rewrite(target, { request: { headers } });
}

export const config = { matcher: "/api/:path*" };
