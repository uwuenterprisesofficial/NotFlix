"use client";

import { useSyncExternalStore } from "react";

/** Why the desktop app didn't take a backend address. */
export type BackendError = "invalid" | "unreachable" | "notNotflix" | "wrongKey" | "missingKey";

/** What the desktop app's preload script offers the page (see desktop/preload.js). */
export type DesktopBridge = {
  /** The backend this app talks to (null before one was chosen), and whether its API key is
   * saved (the key itself stays in the app). */
  backend(): Promise<{ url: string | null; hasKey: boolean }>;
  /** Check the address and key, and switch to them; the app reloads on success. An empty key
   * keeps the saved one. */
  setBackend(
    url: string,
    key: string,
  ): Promise<{ ok: true } | { ok: false; error: BackendError }>;
};

declare global {
  interface Window {
    notflixDesktop?: DesktopBridge;
  }
}

const never = () => () => {};

/** The desktop app's bridge; null in a browser (and while rendering on the server). */
export function useDesktop(): DesktopBridge | null {
  return useSyncExternalStore(
    never,
    () => window.notflixDesktop ?? null,
    () => null,
  );
}
