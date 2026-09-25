"use client";

import { useParams, usePathname, useRouter, useSearchParams } from "next/navigation";
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
import type { Connection, Person, Presence, RoomOut, RoomState, RoomStream } from "@/lib/types";

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
  partner: Person | null;
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
  /** This page without Watch Together. */
  leaveHref: string;
};

const PartyContext = createContext<Party | null>(null);

export function useWatchParty() {
  return use(PartyContext);
}

/**
 * Watch Together on the watch pages (`?together=<connection id>`): the room's state and who's
 * there, from the server's event stream, and changes sent to it. It lives in the watch layout,
 * so it stays connected across episodes. When the partner starts another episode, this page
 * follows.
 */
export function WatchPartyProvider({ me, children }: { me: number | null; children: ReactNode }) {
  const search = useSearchParams();
  const id = Number(search.get("together")) || null;
  return id && me !== null ? (
    <Room key={id} connectionId={id} me={me}>
      {children}
    </Room>
  ) : (
    children
  );
}

function Room({
  connectionId,
  me,
  children,
}: {
  connectionId: number;
  me: number;
  children: ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const params = useParams<{ id: string; episode?: string }>();
  const animeId = Number(params.id);
  const episode = params.episode ? Number(params.episode) : null;

  const [state, setState] = useState<RoomState | null>(null);
  const [members, setMembers] = useState<Presence[]>([]);
  const [ready, setReady] = useState(false);
  const [offline, setOffline] = useState(false);
  const [partner, setPartner] = useState<Person | null>(null);
  const current = useRef<RoomState | null>(null);
  // Server clock minus ours, from the request with the shortest round trip so far.
  const clock = useRef({ offset: 0, rtt: Infinity });

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
    // The clock first, and the partner's name.
    void timed(`/api/together/${connectionId}/room`).then(({ body }) => {
      if (!cancelled && body) accept((body as RoomOut).state);
    });
    fetch("/api/together")
      .then((r) => (r.ok ? r.json() : []))
      .then((all: Connection[]) => {
        if (!cancelled) setPartner(all.find((c) => c.id === connectionId)?.partner ?? null);
      })
      .catch(() => {});
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
      }
      if (gotState && gotPresence) setReady(true);
    };
    return () => {
      events.close();
      setReady(false); // the next page's stream says again
    };
  }, [connectionId, animeId, episode, accept]);

  // The partner started another episode: follow them.
  const followed = useRef(0);
  useEffect(() => {
    if (!state || state.by === me || state.action !== "load" || followed.current >= state.rev)
      return;
    if (state.anime_id === animeId && state.episode === episode) return;
    followed.current = state.rev;
    router.push(watchHref(state, connectionId));
  }, [state, me, animeId, episode, connectionId, router]);

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

  const leave = new URLSearchParams(search.toString());
  leave.delete("together");
  const leaveHref = `${pathname}${leave.size ? `?${leave}` : ""}`;

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
      leaveHref,
    }),
    [connectionId, me, partner, state, members, ready, offline, serverNow, send, leaveHref],
  );
  return <PartyContext value={party}>{children}</PartyContext>;
}
