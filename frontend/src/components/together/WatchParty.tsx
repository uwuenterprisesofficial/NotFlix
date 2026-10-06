"use client";

import { useParams, useRouter } from "next/navigation";
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
import { watchHref } from "@/lib/together";
import type { Person, Presence, RoomOut, RoomState, RoomStream } from "@/lib/types";

export type RoomUpdate = {
  action: RoomState["action"];
  anime_id: number;
  episode: number;
  position: number;
  playing?: boolean;
  stream?: RoomStream | null;
};

export type Party = {
  connectionId: number;
  me: number;
  partner: Person;
  /** What the room plays; null before anything was started in it. */
  state: RoomState | null;
  members: Presence[];
  /** The room's state has arrived (so it's known whether this page matches it). */
  ready: boolean;
  /** The event stream is down (it reconnects by itself). */
  offline: boolean;
  /** The server's clock (ms): room positions are timed by it. */
  serverNow: () => number;
  send: (update: RoomUpdate) => void;
  /** End the session (for both). */
  leave: () => void;
};

// A partner's episode start older than this when the room is opened isn't followed anymore.
const FOLLOW_FRESH_MS = 20_000;

const PartyContext = createContext<Party | null>(null);

/** The active Watch Together session's room; null without one. */
export function useWatchParty() {
  return use(PartyContext);
}

export function PartyProvider({ party, children }: { party: Party | null; children: ReactNode }) {
  return <PartyContext value={party}>{children}</PartyContext>;
}

/**
 * An active Watch Together session's room (see Session.tsx), anywhere in the app: the room's
 * state and who's there, from the server's event stream, and changes sent to it, handed to
 * `onChange` (for a PartyProvider: the page around it isn't remounted when a session starts or
 * ends). When the partner starts an episode, this side follows, from whatever page it's on.
 */
export function Room({
  connectionId,
  me,
  partner,
  onSessionChange,
  leave,
  onChange,
}: {
  connectionId: number;
  me: number;
  partner: Person;
  /** The session changed (e.g. the partner left). */
  onSessionChange: () => void;
  leave: () => void;
  onChange: (party: Party | null) => void;
}) {
  const router = useRouter();
  const params = useParams<{ id?: string; episode?: string }>();
  // On a watch page: the show and episode it plays.
  const episode = params.episode ? Number(params.episode) : null;
  const animeId = episode !== null && params.id ? Number(params.id) : null;

  const [state, setState] = useState<RoomState | null>(null);
  const [members, setMembers] = useState<Presence[]>([]);
  const [ready, setReady] = useState(false);
  const [offline, setOffline] = useState(false);
  const current = useRef<RoomState | null>(null);
  // Server clock minus ours, from the request with the shortest round trip so far.
  const clock = useRef({ offset: 0, rtt: Infinity });
  const sessionChanged = useRef(onSessionChange);
  useEffect(() => {
    sessionChanged.current = onSessionChange;
  });

  const accept = useCallback((next: RoomState | null) => {
    const cur = current.current;
    if (!next) return;
    if (cur && next.rev < cur.rev) return; // an older change arriving late
    current.current = next;
    setState(next);
  }, []);

  const timed = useCallback(async (input: string, init?: RequestInit) => {
    const sent = Date.now();
    const res = await fetch(input, init);
    const body = await res.json().catch(() => null);
    const rtt = Date.now() - sent;
    if (res.ok && body?.now && rtt <= clock.current.rtt) {
      clock.current = { offset: body.now - (sent + rtt / 2), rtt };
    }
    return { res, body };
  }, []);

  const serverNow = useCallback(() => Date.now() + clock.current.offset, []);

  useEffect(() => {
    let cancelled = false;
    void timed(`/api/together/${connectionId}/room`).then(({ body }) => {
      if (!cancelled && body) accept((body as RoomOut).state);
    });
    return () => {
      cancelled = true;
    };
  }, [connectionId, timed, accept]);

  useEffect(() => {
    const query = new URLSearchParams();
    if (animeId) query.set("anime_id", String(animeId));
    if (episode) query.set("episode", String(episode));
    const events = new EventSource(`/api/together/${connectionId}/room/events?${query}`);
    // Ready once both the room's state and who's in it are known (for this page): a player
    // that settled before knowing the partner is there would take itself for the first one.
    let gotState = false;
    let gotPresence = false;
    events.onopen = () => setOffline(false);
    events.onerror = () => setOffline(true);
    events.onmessage = (e) => {
      const msg = JSON.parse(e.data);
      if (msg.type === "state") {
        accept(msg.state);
        gotState = true;
      } else if (msg.type === "presence") {
        setMembers(msg.members);
        gotPresence = true;
      } else if (msg.type === "session") {
        sessionChanged.current();
      }
      if (gotState && gotPresence) setReady(true);
    };
    return () => {
      events.close();
      setReady(false); // the next page's stream says again
    };
  }, [connectionId, animeId, episode, accept]);

  // The partner started an episode: open it here too (it plays by itself), from any page. What
  // the room had when it was opened (e.g. after a reload) only if it was started just now.
  const followed = useRef<number | null>(null);
  useEffect(() => {
    if (!state) return;
    const first = followed.current === null;
    if (!first && followed.current! >= state.rev) return;
    followed.current = state.rev;
    if (state.by === me || state.action !== "load") return;
    if (first && serverNow() - state.at > FOLLOW_FRESH_MS) return;
    if (state.anime_id === animeId && state.episode === episode) return;
    router.push(watchHref(state));
  }, [state, me, animeId, episode, router, serverNow]);

  const send = useCallback(
    (update: RoomUpdate) => {
      const cur = current.current;
      // Right away here; the server's answer (with its order) replaces it.
      if (cur && cur.anime_id === update.anime_id && cur.episode === update.episode) {
        const playing =
          update.action === "play"
            ? true
            : update.action === "pause"
              ? false
              : (update.playing ?? cur.playing);
        const moved = update.action !== "stream";
        const optimistic: RoomState = {
          ...cur,
          action: update.action,
          by: me,
          playing,
          position: moved ? update.position : cur.position,
          at: moved ? serverNow() : cur.at,
          stream: update.stream ?? cur.stream,
        };
        current.current = optimistic;
        setState(optimistic);
      }
      void timed(`/api/together/${connectionId}/room`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(update),
      }).then(({ res, body }) => {
        if (res.ok) accept((body as RoomOut).state);
        else if (res.status === 409 && body?.detail?.state) accept(body.detail.state);
      });
    },
    [connectionId, me, serverNow, timed, accept],
  );

  const party = useMemo<Party>(
    () => ({
      connectionId,
      me,
      partner,
      state,
      members,
      ready,
      offline,
      serverNow,
      send,
      leave,
    }),
    [connectionId, me, partner, state, members, ready, offline, serverNow, send, leave],
  );
  useEffect(() => onChange(party), [party, onChange]);
  useEffect(() => () => onChange(null), [onChange]);
  return null;
}
