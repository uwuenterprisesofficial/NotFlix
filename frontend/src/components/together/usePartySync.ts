"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { expectedPosition } from "@/lib/together";
import type { Party } from "./WatchParty";

// Further off than this, the video jumps to the room's position; closer, it plays a little
// faster or slower until it's back in step.
const HARD_DRIFT_S = 1;
const SOFT_DRIFT_S = 0.25;
const CATCH_UP_RATE = 0.1;
const MIN_HARD_SEEK_GAP_MS = 3000; // a slow connection mustn't seek in a loop
// A seek by the viewer further than this from the room's position is sent to the partner.
const SEEK_TOLERANCE_S = 1.5;
const CHECK_EVERY_MS = 1000;

/**
 * Keeps a <video> in step with a Watch Together room. The viewer's own play, pause and seeks
 * go to the room (and so to the partner); the room's changes are applied here. Whatever this
 * hook does to the video itself (following the room) isn't sent back: a change is only sent
 * when the video no longer matches the room.
 *
 * Nothing is sent before the video is loaded and has caught up with the room once, so opening
 * a page (or a stream failing over) never moves the partner. The video doesn't autoplay in a
 * room: it starts when the room plays; after starting an episode for both, the first load
 * starts it for both.
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
  const everPlayed = useRef(false);
  const lastHardSeek = useRef(0);
  const ownSeek = useRef<number | null>(null);

  const room = useCallback(() => {
    const s = latest.current?.state;
    return s && s.anime_id === animeId && s.episode === episode ? s : null;
  }, [animeId, episode]);

  const seekTo = useCallback((video: HTMLVideoElement, at: number) => {
    ownSeek.current = at;
    video.currentTime = at;
  }, []);

  const play = useCallback((video: HTMLVideoElement) => {
    video.play().then(
      () => setBlocked(false),
      (e: DOMException) => e.name === "NotAllowedError" && setBlocked(true),
    );
  }, []);

  /** Bring the video in step with the room. */
  const apply = useCallback(() => {
    const video = ref.current;
    const p = latest.current;
    const s = room();
    if (!video || !p || !s || video.readyState < 1 || video.seeking) return;
    const target = expectedPosition(s, p.serverNow());
    const drift = video.currentTime - target;
    if (s.playing) {
      if (video.duration && target >= video.duration - 0.5) return; // the partner is past the end
      if (Math.abs(drift) > HARD_DRIFT_S) {
        if (Date.now() - lastHardSeek.current > MIN_HARD_SEEK_GAP_MS) {
          lastHardSeek.current = Date.now();
          video.playbackRate = 1;
          seekTo(video, target);
        }
      } else if (Math.abs(drift) > SOFT_DRIFT_S) {
        video.playbackRate = drift > 0 ? 1 - CATCH_UP_RATE : 1 + CATCH_UP_RATE;
      } else {
        video.playbackRate = 1;
      }
      if (video.paused && !video.ended) play(video);
    } else {
      video.playbackRate = 1;
      if (!video.paused) video.pause();
      if (Math.abs(drift) > 0.5) seekTo(video, target);
    }
  }, [ref, room, seekTo, play]);

  /** The first time the video is loaded and the room's state known. */
  const settle = useCallback(() => {
    const video = ref.current;
    const p = latest.current;
    if (settled.current || !video || !p?.ready || video.readyState < 1) return;
    const s = room();
    if (!s) return; // the player is starting this episode in the room; its state follows
    settled.current = true;
    const fresh = !everPlayed.current && video.played.length === 0;
    if (s.action === "load" && s.by === p.me && !s.playing && fresh) {
      // This viewer just started the episode for both: go.
      p.send({ action: "play", anime_id: s.anime_id, episode: s.episode, position: s.position });
      if (Math.abs(video.currentTime - s.position) > 0.5) seekTo(video, s.position);
      play(video);
    } else {
      apply();
    }
  }, [ref, room, apply, seekTo, play]);

  // The room changed (or became known).
  const rev = party?.state?.rev;
  const at = party?.state?.at;
  useEffect(() => {
    if (!party) return;
    if (settled.current) apply();
    else settle();
  }, [party, rev, at, apply, settle]);

  // The viewer's own play/pause/seek go to the room; and a regular check for drift.
  const active = party !== null;
  useEffect(() => {
    const video = ref.current;
    if (!video || !active) return;
    const send = (action: "play" | "pause" | "seek", playing?: boolean) => {
      const s = room();
      if (!s || !settled.current) return;
      latest.current?.send({
        action,
        anime_id: s.anime_id,
        episode: s.episode,
        position: video.currentTime,
        playing,
      });
    };
    const onPlay = () => {
      everPlayed.current = true;
      if (!room()?.playing) send("play");
    };
    const onPause = () => {
      if (!video.ended && room()?.playing) send("pause");
    };
    const onSeeked = () => {
      const own = ownSeek.current;
      ownSeek.current = null;
      if (own !== null && Math.abs(video.currentTime - own) < 0.5) return;
      const s = room();
      const p = latest.current;
      if (!s || !p) return;
      if (Math.abs(video.currentTime - expectedPosition(s, p.serverNow())) > SEEK_TOLERANCE_S)
        send("seek", !video.paused);
    };
    const onLoaded = () => setTimeout(settle, 0);
    video.addEventListener("play", onPlay);
    video.addEventListener("pause", onPause);
    video.addEventListener("seeked", onSeeked);
    video.addEventListener("loadedmetadata", onLoaded);
    if (video.readyState >= 1) onLoaded();
    const timer = setInterval(() => settled.current && apply(), CHECK_EVERY_MS);
    return () => {
      video.removeEventListener("play", onPlay);
      video.removeEventListener("pause", onPause);
      video.removeEventListener("seeked", onSeeked);
      video.removeEventListener("loadedmetadata", onLoaded);
      clearInterval(timer);
      video.playbackRate = 1;
    };
  }, [ref, active, room, apply, settle]);

  return {
    blocked,
    /** Start playback with a click, when the browser didn't allow it by itself. */
    unblock: () => {
      const video = ref.current;
      if (video) play(video);
    },
  };
}
