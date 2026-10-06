"use client";

import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import {
  createContext,
  type ReactNode,
  use,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { PENDING_INVITE_KEY, watchHref } from "@/lib/together";
import type { TogetherSession } from "@/lib/types";
import { useT } from "../I18nProvider";
import { Avatar } from "./Avatar";
import { type Party, PartyProvider, Room, useWatchParty } from "./WatchParty";

// How often the sessions are asked for: quicker while waiting for the partner to join.
const POLL_MS = 8000;
const WAITING_POLL_MS = 2500;

type Sessions = {
  me: number;
  sessions: TogetherSession[];
  /** The session both joined: the players follow its room. */
  active: TogetherSession | null;
  /** Start a session with a connection (inviting them), or join the one they started. */
  start: (connectionId: number) => Promise<boolean>;
  /** Leave a session, or turn down an invitation: it ends for both. */
  leave: (connectionId: number) => Promise<void>;
};

const SessionContext = createContext<Sessions | null>(null);

/** Watch Together sessions; null when signed out. */
export function useTogetherSessions() {
  return use(SessionContext);
}

/**
 * Watch Together for a signed-in user, anywhere in the app: invitations to watch, the session
 * waiting for the partner, and the active one's room (which the players follow).
 */
export function TogetherSessions({ me, children }: { me: number | null; children: ReactNode }) {
  if (me === null) return children;
  return <Provider me={me}>{children}</Provider>;
}

function Provider({ me, children }: { me: number; children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [sessions, setSessions] = useState<TogetherSession[]>([]);
  const [party, setParty] = useState<Party | null>(null);
  const reload = useRef<() => void>(() => {});
  // Asks again now (after a change).
  const load = useCallback(() => reload.current(), []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let seq = 0;
    let last = 0;
    const ask = () => {
      clearTimeout(timer);
      if (cancelled || document.visibilityState !== "visible") return;
      const mine = ++seq;
      last = Date.now();
      fetch("/api/together/sessions")
        .then((r) => (r.ok ? r.json() : []))
        .catch(() => [])
        .then((all: TogetherSession[]) => {
          if (cancelled || mine !== seq) return; // a newer one is on its way
          setSessions(all);
          const waiting = all.some((s) => !s.active && s.joined.includes(me));
          timer = setTimeout(ask, waiting ? WAITING_POLL_MS : POLL_MS);
        });
    };
    reload.current = ask;
    // Back to the tab: at once, unless it was just asked.
    const onVisible = () =>
      document.visibilityState === "visible" && Date.now() - last > 1000 && ask();
    ask();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      reload.current = () => {};
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [me]);

  // An invite link opened while signed out: take it up now.
  useEffect(() => {
    let pending: string | null = null;
    try {
      pending = localStorage.getItem(PENDING_INVITE_KEY);
      localStorage.removeItem(PENDING_INVITE_KEY);
    } catch {}
    if (pending && !pathname.startsWith("/together/join/"))
      router.push(`/together/join/${pending}`);
  }, [pathname, router]);

  const start = useCallback(
    async (connectionId: number) => {
      const res = await fetch(`/api/together/${connectionId}/session`, { method: "POST" }).catch(
        () => null,
      );
      if (res?.ok) {
        const joined: TogetherSession = await res.json();
        // Joining one leaves the others.
        setSessions((all) => [...all.filter((s) => !s.joined.includes(me)), joined]);
      }
      load();
      return !!res?.ok;
    },
    [me, load],
  );

  const leave = useCallback(
    async (connectionId: number) => {
      setSessions((all) => all.filter((s) => s.connection_id !== connectionId));
      await fetch(`/api/together/${connectionId}/session`, { method: "DELETE" }).catch(() => {});
      load();
    },
    [load],
  );

  const active = sessions.find((s) => s.active) ?? null;
  const value = useMemo<Sessions>(
    () => ({ me, sessions, active, start, leave }),
    [me, sessions, active, start, leave],
  );
  const leaveActive = useCallback(() => {
    if (active) void leave(active.connection_id);
  }, [active, leave]);

  return (
    <SessionContext value={value}>
      <PartyProvider party={active ? party : null}>
        {children}
        <SessionBar />
      </PartyProvider>
      {active && (
        <Room
          key={active.connection_id}
          connectionId={active.connection_id}
          me={me}
          partner={active.partner}
          onSessionChange={load}
          leave={leaveActive}
          onChange={setParty}
        />
      )}
    </SessionContext>
  );
}

const BAR =
  "fixed bottom-4 left-4 z-50 flex max-w-[calc(100vw-2rem)] items-center gap-3 rounded-lg bg-surface-raised p-2 pl-3 text-sm shadow-2xl ring-1 ring-white/10";

/** Invitations, waiting for the partner, and (away from the player) the active session. */
function SessionBar() {
  const { t } = useT();
  const ctx = useTogetherSessions();
  const party = useWatchParty();
  const params = useParams<{ id?: string; episode?: string }>();
  const [busy, setBusy] = useState(false);
  if (!ctx) return null;
  const { me, sessions, active, start, leave } = ctx;

  if (active && party) {
    // On a watch page the bar under the player says it all.
    if (params.episode) return null;
    const state = party.state;
    return (
      <div role="status" className={BAR}>
        <Avatar person={active.partner} size={24} />
        <span className="min-w-0 flex-1">
          {t("together.sessionActive", { name: active.partner.name })}
          {state?.title && (
            <span className="block truncate text-xs text-muted">
              {t("together.watchingNow", { title: state.title, episode: state.episode })}
            </span>
          )}
        </span>
        {state && (
          <Link
            href={watchHref(state)}
            className="rounded bg-white px-3 py-1 font-semibold text-black"
          >
            ▶ {t("together.join")}
          </Link>
        )}
        <button onClick={party.leave} className="px-2 text-muted hover:text-white">
          {t("together.leave")}
        </button>
      </div>
    );
  }

  const invitation = sessions.find((s) => !s.active && !s.joined.includes(me));
  const waiting = sessions.find((s) => !s.active && s.joined.includes(me));
  const shown = invitation ?? waiting;
  if (!shown) return null;
  return (
    <div role="status" className={BAR}>
      <Avatar person={shown.partner} size={24} />
      {shown === invitation ? (
        <>
          <span className="flex-1">{t("together.invited", { name: shown.partner.name })}</span>
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              await start(shown.connection_id);
              setBusy(false);
            }}
            className="rounded bg-white px-3 py-1 font-semibold text-black disabled:opacity-60"
          >
            {t("together.join")}
          </button>
          <button
            onClick={() => leave(shown.connection_id)}
            className="px-2 text-muted hover:text-white"
          >
            {t("together.notNow")}
          </button>
        </>
      ) : (
        <>
          <span className="flex items-center gap-2">
            <span aria-hidden className="size-2 animate-pulse rounded-full bg-amber-400" />
            {t("together.waitingFor", { name: shown.partner.name })}
          </span>
          <button
            onClick={() => leave(shown.connection_id)}
            className="px-2 text-muted hover:text-white"
          >
            {t("together.cancel")}
          </button>
        </>
      )}
    </div>
  );
}

/** Watch together with a connection: starts the session (inviting them), then opens `href`. */
export function StartSession({
  connectionId,
  href,
  className,
  children,
}: {
  connectionId: number;
  href?: string;
  className?: string;
  children: ReactNode;
}) {
  const ctx = useTogetherSessions();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  return (
    <button
      disabled={busy || !ctx}
      onClick={async () => {
        if (!ctx) return;
        setBusy(true);
        const ok = await ctx.start(connectionId);
        setBusy(false);
        if (ok && href) router.push(href);
      }}
      className={className}
    >
      {children}
    </button>
  );
}
