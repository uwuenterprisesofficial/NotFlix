import { type NextRequest, NextResponse } from "next/server";
import {
  API_KEY_HEADER,
  answeredLocally,
  apiKey,
  backendUrl,
  isDesktop,
  localBackend,
  seriesService,
} from "@/lib/backend";

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
  if (pathname.startsWith("/series-api/")) {
    // The series service on this PC (desktop app only), without the browser's cookies.
    const series = seriesService();
    if (!series) return NextResponse.json({ detail: "No series service" }, { status: 503 });
    const headers = new Headers(request.headers);
    headers.delete("cookie");
    const path = pathname.slice("/series-api".length);
    return NextResponse.rewrite(new URL(`${series}${path}${search}`), { request: { headers } });
  }
  const path = pathname.slice("/api".length);
  const headers = new Headers(request.headers);
  // Hybrid mode: streams are found and played on this PC.
  const local = localBackend();
  if (local && answeredLocally(path)) {
    headers.set(API_KEY_HEADER, local.key);
    return NextResponse.rewrite(new URL(`${local.url}${path}${search}`), { request: { headers } });
  }
  const target = new URL(`${backendUrl()}${path}${search}`);
  // The Host the browser used (nextUrl says "localhost" for 127.0.0.1, which has other cookies).
  // Elsewhere the header passes through: the desktop app may reach the backend through the web
  // app's /api.
  const host = request.headers.get("host");
  if (isDesktop() && host) headers.set(ORIGIN_HEADER, `http://${host}`);
  const key = apiKey();
  if (key) headers.set(API_KEY_HEADER, key);
  return NextResponse.rewrite(target, { request: { headers } });
}

export const config = { matcher: ["/api/:path*", "/series-api/:path*"] };
