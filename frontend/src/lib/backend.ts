/**
 * The FastAPI backend, read when a request is made (not baked in at build time): Docker sets
 * API_INTERNAL_URL per container, and the desktop app starts this server with the backend
 * chosen in its settings.
 */
export function backendUrl(): string {
  return (process.env.API_INTERNAL_URL || "http://localhost:8000").replace(/\/+$/, "");
}

/**
 * The backend's API key (API_KEY), which every request to it needs. Only this server knows it:
 * it's added to the requests passed on, never sent to the browser. Empty: requests pass with
 * whatever key they bring (a web app only forwarding for the desktop app; see the README).
 */
export function apiKey(): string {
  return process.env.API_KEY || "";
}

export const API_KEY_HEADER = "x-api-key";

/** Running inside the desktop app (which starts this server on the user's PC). */
export function isDesktop(): boolean {
  return process.env.NOTFLIX_DESKTOP === "1";
}

/**
 * Hybrid mode (desktop app): the built-in server on this PC (LOCAL_API_URL, its key in
 * LOCAL_API_KEY) finds and plays streams, sharing what it finds with the online server, which
 * does everything else (accounts, lists, Watch Together). Null outside hybrid mode.
 */
export function localBackend(): { url: string; key: string } | null {
  const url = process.env.LOCAL_API_URL;
  if (!url) return null;
  return { url: url.replace(/\/+$/, ""), key: process.env.LOCAL_API_KEY || "" };
}

// What the local server answers in hybrid mode (paths without /api): looking for, resolving
// and relaying streams, and looking up German synopses (both shared with the online server).
const LOCAL_PATHS = [
  /^\/anime\/\d+\/(streams|availability(\/refresh)?|preview|mappings(\/\w+)?|synopsis)$/,
  /^\/anime\/\d+\/episodes\/\d+\/(sources|resolve|failures)$/,
  /^\/proxy(\/|$)/,
  /^\/providers$/,
  /^\/prefetch$/,
];

export function answeredLocally(path: string): boolean {
  return LOCAL_PATHS.some((pattern) => pattern.test(path));
}
