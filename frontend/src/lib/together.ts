import type { RoomState } from "./types";

/** Where a Watch Together room's playback is at a server time (ms): it moves on while playing. */
export function expectedPosition(state: RoomState, serverNow: number) {
  return state.playing ? state.position + Math.max(0, serverNow - state.at) / 1000 : state.position;
}

/** The watch page a room is on, in that room, with the stream it plays. */
export function watchHref(state: RoomState, connectionId: number) {
  const params = new URLSearchParams({ together: String(connectionId) });
  if (state.stream?.provider) params.set("via", state.stream.provider);
  if (state.stream?.label) params.set("option", state.stream.label);
  if (state.stream?.server) params.set("server", state.stream.server);
  return `/watch/${state.anime_id}/${state.episode}?${params}`;
}

/** An invite link opened while signed out: taken up again after signing in. */
export const PENDING_INVITE_KEY = "notflix:invite";
