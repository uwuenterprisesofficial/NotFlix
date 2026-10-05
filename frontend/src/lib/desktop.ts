"use client";

import { useSyncExternalStore } from "react";

/** Why the desktop app didn't take a backend address. */
export type BackendError = "invalid" | "unreachable" | "notNotflix";

/** What the desktop app's preload script offers the page (see desktop/preload.js). */
export type DesktopBridge = {
  /** The backend this app talks to, or null before one was chosen. */
  backend(): Promise<string | null>;
  /** Check the address and switch to it; the app reloads on success. */
  setBackend(url: string): Promise<{ ok: true } | { ok: false; error: BackendError }>;
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
