"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { PENDING_INVITE_KEY, watchHref } from "@/lib/together";
import type { Connection } from "@/lib/types";
import { useT } from "../I18nProvider";

const POLL_MS = 20_000;
const IDLE_POLL_MS = 5 * 60_000;

/**
 * Anywhere in the app: "Anna is watching X · Episode 3 — Join" while a connection is watching in
 * your room without you. Also takes up an invite link that was opened before signing in.
 */
export function TogetherToast() {
  const { t } = useT();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [dismissed, setDismissed] = useState<string[]>([]);

  useEffect(() => {
    let pending: string | null = null;
    try {
      pending = localStorage.getItem(PENDING_INVITE_KEY);
      localStorage.removeItem(PENDING_INVITE_KEY);
    } catch {}
    if (pending && !pathname.startsWith("/together/join/"))
      router.push(`/together/join/${pending}`);
  }, [pathname, router]);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let last = 0;
    // Someone without connections is asked rarely (they may accept an invite elsewhere).
    const load = () => {
      clearTimeout(timer);
      if (cancelled || document.visibilityState !== "visible") return;
      last = Date.now();
      fetch("/api/together")
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => [])
        .then((all: Connection[]) => {
          if (cancelled) return;
          setConnections(all);
          timer = setTimeout(load, all.length ? POLL_MS : IDLE_POLL_MS);
        });
    };
    // Back to the tab: at once, unless it was just asked.
    const onVisible = () =>
      document.visibilityState === "visible" && Date.now() - last > POLL_MS / 2 && load();
    load();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  const inRoom = search.get("together");
  const shown = connections.find((c) => {
    const s = c.partner_watching;
    return (
      s && String(c.id) !== inRoom && !dismissed.includes(`${c.id}:${s.anime_id}:${s.episode}`)
    );
  });
  const state = shown?.partner_watching;
  if (!shown || !state) return null;

  return (
    <div
      role="status"
      className="fixed right-4 bottom-4 z-50 flex max-w-sm items-center gap-3 rounded-lg bg-surface-raised p-3 pl-4 text-sm shadow-2xl ring-1 ring-white/10"
    >
      <span aria-hidden className="size-2 shrink-0 rounded-full bg-green-400" />
      <span className="flex-1">
        {t("together.toast", {
          name: shown.partner.name,
          title: state.title ?? "?",
          episode: state.episode,
        })}
      </span>
      <Link
        href={watchHref(state, shown.id)}
        onClick={() =>
          setDismissed((d) => [...d, `${shown.id}:${state.anime_id}:${state.episode}`])
        }
        className="rounded bg-white px-3 py-1 font-semibold text-black"
      >
        {t("together.join")}
      </Link>
      <button
        onClick={() =>
          setDismissed((d) => [...d, `${shown.id}:${state.anime_id}:${state.episode}`])
        }
        aria-label={t("together.dismiss")}
        className="px-1 text-muted hover:text-white"
      >
        ✕
      </button>
    </div>
  );
}
