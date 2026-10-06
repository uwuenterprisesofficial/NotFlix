"use client";

import { useSyncExternalStore } from "react";

/** Why the desktop app didn't take a backend address. */
export type BackendError =
  | "invalid"
  | "unreachable"
  | "notNotflix"
  | "wrongKey"
  | "missingKey"
  | "builtInFailed";

/** The built-in server's settings (secrets only as whether they're saved). */
export type BuiltInSettings = {
  malClientId: string;
  hasMalSecret: boolean;
  anilistClientId: string;
  hasAnilistSecret: boolean;
  /** Where AniWorld comes from: AniScraper (direct streams) or SerienStreamAPI (embeds). */
  aniworldVia: "aniscraper" | "serienstream";
};

/** What's sent to change them; empty secrets keep the saved ones. */
export type BuiltInUpdate = Omit<BuiltInSettings, "hasMalSecret" | "hasAnilistSecret"> & {
  malClientSecret: string;
  anilistClientSecret: string;
};

export type DesktopBackend = {
  /** The built-in server on this PC, or another server. */
  mode: "builtin" | "remote";
  /** The other server's address (null before one was chosen), and whether its API key is
   * saved (the key itself stays in the app). */
  url: string | null;
  hasKey: boolean;
  /** Hybrid mode (with another server): streams are found and played by the built-in server on
   * this PC, which shares what it finds with the other server; the rest is the other server's. */
  hybrid: boolean;
  /** Null when the app was built without the built-in server. */
  builtIn: {
    /** Why it didn't start, if it didn't. */
    error: string | null;
    settings: BuiltInSettings;
    /** SerienStreamAPI's AniWorld service is part of it. */
    serienStream: boolean;
  } | null;
};

export type RemoteOptions = {
  hybrid: boolean;
  aniworldVia: BuiltInSettings["aniworldVia"];
};

type Result = { ok: true } | { ok: false; error: BackendError };

/** What the desktop app's preload script offers the page (see desktop/preload.js). */
export type DesktopBridge = {
  backend(): Promise<DesktopBackend>;
  /** Use another server: checks the address and key, and switches to them (the app reloads).
   * An empty key keeps the saved one. `options.hybrid`: find and play streams on this PC. */
  setBackend(url: string, key: string, options?: RemoteOptions): Promise<Result>;
  /** Use the built-in server with these settings (it restarts, and the app reloads). */
  setBuiltIn(settings: BuiltInUpdate): Promise<Result>;
  /** Open the built-in server's log folder. */
  openLogs(): Promise<void>;
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
