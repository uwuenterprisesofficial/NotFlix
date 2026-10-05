/**
 * The FastAPI backend, read when a request is made (not baked in at build time): Docker sets
 * API_INTERNAL_URL per container, and the desktop app starts this server with the backend
 * chosen in its settings.
 */
export function backendUrl(): string {
  return (process.env.API_INTERNAL_URL || "http://localhost:8000").replace(/\/+$/, "");
}

/** Running inside the desktop app (which starts this server on the user's PC). */
export function isDesktop(): boolean {
  return process.env.NOTFLIX_DESKTOP === "1";
}
