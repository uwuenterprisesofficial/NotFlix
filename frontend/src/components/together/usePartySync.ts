"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { expectedPosition } from "@/lib/together";
import type { Party } from "./WatchParty";

// With the partner there: further off than this, the video jumps to the room's position;
// closer, it plays a little faster or slower (up to MAX_RATE_OFFSET) until it's back in step.
// Jumping means buffering, so it's the last resort.
const HARD_DRIFT_S = 4;
const SOFT_DRIFT_S = 0.5;
const MAX_RATE_OFFSET = 0.15;
// After a jump (or while buffering) the video isn't corrected: it has to load first.
const QUIET_AFTER_SEEK_MS = 5000;
// A seek by the viewer further than this from the room's position is sent to the partner.
const SEEK_TOLERANCE_S = 1.5;
// Alone: the room's clock is corrected (for a partner joining later) when this far off.
const REANCHOR_S = 2;
// Without the room's state by then, the video starts anyway, as it would alone.
const READY_TIMEOUT_MS = 1500;
const CHECK_EVERY_MS = 1000;

/**
 * Keeps a <video> in step with a Watch Together room.
 *
 * Alone in the room (the partner isn't on this episode), the video plays exactly as without a
 * room: it starts by itself, resumes where it was, and nothing is ever corrected. It only
 * tells the room where it is (play, pause, seeks, and its position when the room's clock
 * drifted, e.g. after buffering), so a partner who joins starts right there.
 *
 * With the partner there, each side's own play, pause and seeks go to the room, and the room's
 * changes are applied here. Whatever this hook does to the video itself isn't sent back: a
 * change is only sent when the video no longer matches the room. The video is never corrected
 * while it's buffering or has just jumped, and small differences are caught up by playing a
 * little faster or slower, so a slow stream isn't made to jump (and buffer) over and over.
 *
 * Nothing is sent before the room's state is known and the video has caught up with it once,
 * so opening a page (or a stream failing over) never moves the partner.
 */
export function usePartySync(
  ref: React.RefObject<HTMLVideoElement | null>,
  party: Party | null,
  animeId: number | null,
  episode: number | null,
) {
  // The browser refused to start playback without a click (autoplay policy).
  const [blocked, setBlocked] = useState(false);
  const latest = useRef(party);
  useEffect(() => {
    latest.current = party;
  }, [party]);
  const settled = useRef(false);
  const waitedForRoom = useRef(false);
  const wasAlone = useRef(false);
  const buffering = useRef(false);
  const lastSeek = useRef(0);
  const ownSeek = useRef<number | null>(null);

  const room = useCallback(() => {
    const s = latest.current?.state;
    return s && s.anime_id === animeId && s.episode === episode ? s : null;
  }, [animeId, episode]);

  /** The partner has this episode open too. */
  const together = useCallback(() => {
    const p = latest.current;
    return !!p?.members.some(
      (m) => m.user_id !== p.me && m.anime_id === animeId && m.episode === episode,
    );
  }, [animeId, episode]);

  const seekTo = useCallback((video: HTMLVideoElement, at: number) => {
    ownSeek.current = at;
    lastSeek.current = Date.now();
    video.currentTime = at;
  }, []);

  const play = useCallback((video: HTMLVideoElement) => {
    video.play().then(
      () => setBlocked(false),
      (e: DOMException) => e.name === "NotAllowedError" && setBlocked(true),
    );
  }, []);

  const send = useCallback(
    (action: "play" | "pause" | "seek", playing?: boolean) => {
      const video = ref.current;
      const p = latest.current;
      const s = room();
      if (!video || !p?.ready || !s || !settled.current) return;
      p.send({
        action,
        anime_id: s.anime_id,
        episode: s.episode,
        position: video.currentTime,
        playing,
      });
    },
    [ref, room],
  );

  /** With the partner: bring the video in step with the room. */
  const apply = useCallback(() => {
    const video = ref.current;
    const p = latest.current;
    const s = room();
    if (!video || !p || !s || video.readyState < 1) return;
    const target = expectedPosition(s, p.serverNow());
    const drift = video.currentTime - target;
    if (!s.playing) {
      video.playbackRate = 1;
      if (!video.paused) video.pause();
      if (Math.abs(drift) > 0.5 && !video.seeking) seekTo(video, target);
      return;
    }
    if (video.duration && target >= video.duration - 0.5) return; // the partner is past the end
    if (video.paused && !video.ended) {
      if (Math.abs(drift) > SOFT_DRIFT_S) seekTo(video, target);
      play(video);
      return;
    }
    const loading =
      buffering.current || video.seeking || video.readyState < HTMLMediaElement.HAVE_FUTURE_DATA;
    if (loading || Date.now() - lastSeek.current < QUIET_AFTER_SEEK_MS) {
      video.playbackRate = 1;
      return;
    }
    if (Math.abs(drift) > HARD_DRIFT_S) {
      video.playbackRate = 1;
      seekTo(video, target);
    } else if (Math.abs(drift) > SOFT_DRIFT_S) {
      // Behind: a little faster; ahead: a little slower.
      const offset = Math.max(-MAX_RATE_OFFSET, Math.min(MAX_RATE_OFFSET, drift * 0.1));
      video.playbackRate = 1 - offset;
    } else {
      video.playbackRate = 1;
    }
  }, [ref, room, seekTo, play]);

  /** Alone: keep the room's state on this video's, for a partner who joins. */
  const report = useCallback(() => {
    const video = ref.current;
    const p = latest.current;
    const s = room();
    if (!video || !p || !s || video.ended) return;
    if (video.paused === s.playing) {
      send(video.paused ? "pause" : "play");
    } else if (video.paused) {
      if (Math.abs(video.currentTime - s.position) > 0.5) send("seek", false);
    } else if (!buffering.current && !video.seeking) {
      const drift = video.currentTime - expectedPosition(s, p.serverNow());
      if (Math.abs(drift) > REANCHOR_S) send("seek", true);
    }
  }, [ref, room, send]);

  /** Once the video is loaded and the room's state is known (or took too long). */
  const settle = useCallback(() => {
    const video = ref.current;
    const p = latest.current;
    // Not while the player jumps to where it resumes: that's this page's own business.
    if (settled.current || !video || !p || video.readyState < 1 || video.seeking) return;
    if (!p.ready && !waitedForRoom.current) return;
    const s = room();
    const fresh = video.played.length === 0;
    if (p.ready && s && together()) {
      settled.current = true;
      if (s.action === "load" && s.by === p.me && !s.playing && fresh) {
        // This viewer just started the episode for both: go.
        send("play");
        play(video);
      } else {
        apply();
      }
      return;
    }
    // Alone: as without a room (it doesn't autoplay in a room, so start it here).
    settled.current = p.ready;
    wasAlone.current = true;
    if (fresh) play(video);
  }, [ref, room, together, apply, send, play]);

  /** Alone: report; with the partner: follow the room. Whoever was here first tells the room
   * where their video really is when the partner arrives, before anything is corrected. */
  const step = useCallback(() => {
    const video = ref.current;
    if (!video || !latest.current?.ready || !settled.current) return;
    if (!together()) {
      wasAlone.current = true;
      if (video.playbackRate !== 1) video.playbackRate = 1;
      report();
    } else if (wasAlone.current) {
      wasAlone.current = false;
      send("seek", !video.paused);
    } else {
      apply();
    }
  }, [ref, together, report, send, apply]);

  // The room changed (or became known), or someone came or went.
  const rev = party?.state?.rev;
  const at = party?.state?.at;
  const members = party?.members;
  useEffect(() => {
    if (!party) return;
    if (!settled.current) settle();
    else step();
  }, [party, rev, at, members, settle, step]);

  const active = party !== null;
  useEffect(() => {
    const video = ref.current;
    if (!video || !active) return;
    const onPlay = () => {
      if (!room()?.playing) send("play");
    };
    const onPause = () => {
      if (!video.ended && room()?.playing) send("pause");
    };
    const onSeeked = () => {
      const own = ownSeek.current;
      ownSeek.current = null;
      if (own !== null && Math.abs(video.currentTime - own) < 0.5) return;
      if (!settled.current) {
        settle();
        return;
      }
      const s = room();
      const p = latest.current;
      if (!s || !p) return;
      if (Math.abs(video.currentTime - expectedPosition(s, p.serverNow())) > SEEK_TOLERANCE_S)
        send("seek", !video.paused);
    };
    const onWaiting = () => (buffering.current = true);
    const onPlaying = () => (buffering.current = false);
    let readyTimer: ReturnType<typeof setTimeout> | undefined;
    const onLoaded = () => {
      setTimeout(settle, 0);
      readyTimer = setTimeout(() => {
        waitedForRoom.current = true;
        settle();
      }, READY_TIMEOUT_MS);
    };
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("waiting", onWaiting);
    video.addEventListener("playing", onPlaying);
    video.addEventListener("loadedmetadata", onLoaded);
    if (video.readyState >= 1) onLoaded();

    const timer = setInterval(step, CHECK_EVERY_MS);
    return () => {
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("waiting", onWaiting);
      video.removeEventListener("playing", onPlaying);
      video.removeEventListener("loadedmetadata", onLoaded);
      clearTimeout(readyTimer);
      clearInterval(timer);
      video.playbackRate = 1;
    };
  }, [ref, active, room, settle, send, step]);

  return {
    blocked,
    /** Start playback with a click, when the browser didn't allow it by itself. */
    unblock: () => {
      const video = ref.current;
      if (video) play(video);
    },
  };
}
