"use client";

import type Hls from "hls.js";
import { useEffect, useRef, useState } from "react";
import { formatTime } from "@/lib/format";
import type { SkipSegment, Stream } from "@/lib/types";
import { useT } from "../I18nProvider";
import type { Party } from "../together/WatchParty";
import { usePartySync } from "../together/usePartySync";
import { FullscreenButton, useFrameFullscreen } from "./PlayerFrame";

function useStream(
  ref: React.RefObject<HTMLVideoElement | null>,
  url: string,
  isHls: boolean,
  onFatal: React.RefObject<() => void>,
) {
  useEffect(() => {
    const video = ref.current;
    if (!video) return;
    if (!isHls || video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = url;
      return;
    }
    let hls: Hls | undefined;
    let cancelled = false;
    import("hls.js").then(({ default: HlsClass }) => {
      if (cancelled || !HlsClass.isSupported()) return;
      hls = new HlsClass();
      hls.on(HlsClass.Events.ERROR, (_event, data) => data.fatal && onFatal.current());
      hls.loadSource(url);
      hls.attachMedia(video);
    });
    return () => {
      cancelled = true;
      hls?.destroy();
    };
  }, [ref, url, isHls, onFatal]);
}

const NEXT_COUNTDOWN_S = 10;
const SAVE_EVERY_S = 15;
const RESUME_NOTE_MS = 8000;
// Without known intro times: jump the length of a typical opening, early in the episode.
const SKIP_AHEAD_S = 85;
const SKIP_AHEAD_UNTIL_S = 8 * 60;
// A stream that hasn't loaded anything by then counts as broken.
const LOAD_TIMEOUT_MS = 20_000;
// Without detected credits, the "Next Episode" card shows this long before the end (1:30).
const FALLBACK_CREDITS_S = 90;
// Controls drawn over the video hide after the pointer rests this long.
const IDLE_MS = 2500;

/** When the credits start: the detected ending, else 1:30 before the end (at least halfway). */
function creditsStart(ending: SkipSegment | undefined, duration: number) {
  if (ending) return ending.start_s;
  return duration ? Math.max(duration - FALLBACK_CREDITS_S, duration / 2) : Infinity;
}

function typingIn(target: EventTarget | null) {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName))
  );
}

export type NextEpisode = { label: string; go: () => void };

/**
 * A <video> we fully control, so the Netflix-style controls work (unlike cross-origin iframes):
 * "Skip Intro" while the opening plays, and a "Next Episode" card during the credits that starts
 * the next episode after a countdown.
 */
export function DirectVideo({
  stream,
  segments,
  autoSkip,
  autoNext,
  next,
  onNearEnd,
  onStart,
  onFail,
  resumeFrom,
  onPosition,
  resumedAt = null,
  onSave,
  onPlayState,
  sync = null,
}: {
  stream: Stream;
  segments: SkipSegment[];
  autoSkip: boolean;
  autoNext: boolean;
  next: NextEpisode | null;
  onNearEnd: () => void;
  /** Playback started. */
  onStart?: () => void;
  /** The stream can't be played (error, or nothing loaded in time). */
  onFail?: () => void;
  /** Where to start, e.g. the position of a stream that failed mid-episode. */
  resumeFrom?: () => number;
  onPosition?: (seconds: number) => void;
  /** Where this episode was stopped last time (resume watching): shows "Start over". */
  resumedAt?: number | null;
  /** Remember the position: every little while, on pause, and when the tab goes away
   * (`final`: the page may be closing, so it must go out right away). */
  onSave?: (position: number, duration: number, final: boolean) => void;
  onPlayState?: (playing: boolean) => void;
  /** Watch Together: play in step with the room. */
  sync?: { party: Party; animeId: number; episode: number } | null;
}) {
  const { t } = useT();
  const ref = useRef<HTMLVideoElement>(null);
  const autoSkipped = useRef(false);
  const loaded = useRef(false);
  const fail = useRef(() => {});
  useEffect(() => {
    fail.current = () => onFail?.();
  }, [onFail]);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [creditsDismissed, setCreditsDismissed] = useState(false);
  const [paused, setPaused] = useState(true);
  const [idle, setIdle] = useState(true);
  const idleTimer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const fullscreen = useFrameFullscreen();
  const [resumeNote, setResumeNote] = useState(false);
  const lastSave = useRef(0);
  const save = useRef<(final: boolean) => void>(() => {});
  useEffect(() => {
    save.current = (final) => {
      const video = ref.current;
      if (!video || !onSave || !loaded.current || !video.duration) return;
      lastSave.current = video.currentTime;
      onSave(video.currentTime, video.duration, final);
    };
  }, [onSave]);
  // Closing the tab, switching away or navigating: save where playback is.
  useEffect(() => {
    const away = () => document.visibilityState === "hidden" && save.current(true);
    const leave = () => save.current(true);
    document.addEventListener("visibilitychange", away);
    window.addEventListener("pagehide", leave);
    return () => {
      document.removeEventListener("visibilitychange", away);
      window.removeEventListener("pagehide", leave);
      save.current(true); // e.g. the next episode or another page in the app
    };
  }, []);

  const { toggle: toggleFullscreen, supported: canFullscreen } = fullscreen;
  useEffect(() => {
    if (!canFullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "f" || e.ctrlKey || e.metaKey || e.altKey) return;
      if (typingIn(e.target)) return;
      e.preventDefault();
      toggleFullscreen();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [canFullscreen, toggleFullscreen]);
  useEffect(() => () => clearTimeout(idleTimer.current), []);
  useStream(ref, stream.url, stream.format === "hls", fail);
  const partySync = usePartySync(
    ref,
    sync?.party ?? null,
    sync?.animeId ?? null,
    sync?.episode ?? null,
  );

  useEffect(() => {
    const timer = setTimeout(() => loaded.current || fail.current(), LOAD_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, []);

  const opening = segments.find((s) => s.kind === "opening");
  const ending = segments.find((s) => s.kind === "ending");
  const inIntro = !!opening && time >= opening.start_s && time < opening.end_s - 0.5;
  const creditsAt = creditsStart(ending, duration);
  const inCredits = time >= creditsAt;

  function onTimeUpdate() {
    const video = ref.current;
    if (!video) return;
    const t = video.currentTime;
    setTime(t);
    onPosition?.(t);
    // Auto-skip the intro once; seeking back into it afterwards plays it normally.
    if (opening && autoSkip && !autoSkipped.current && t >= opening.start_s && t < opening.end_s) {
      autoSkipped.current = true;
      video.currentTime = opening.end_s;
    }
    if (t >= creditsStart(ending, video.duration)) onNearEnd();
    if (!video.paused && Math.abs(t - lastSave.current) >= SAVE_EVERY_S) save.current(false);
  }

  function wake() {
    setIdle(false);
    clearTimeout(idleTimer.current);
    idleTimer.current = setTimeout(() => setIdle(true), IDLE_MS);
  }

  return (
    <div
      className={`absolute inset-0 ${fullscreen.active && idle && !paused ? "cursor-none" : ""}`}
      onPointerMove={wake}
      onPointerLeave={() => setIdle(true)}
    >
      <video
        ref={ref}
        controls
        // Fullscreen goes to the player frame instead (button, double-click, "f"), so Skip Intro
        // and Next Episode stay visible; the <video>'s own fullscreen would hide them.
        controlsList={fullscreen.supported ? "nofullscreen" : undefined}
        onDoubleClick={(e) => {
          if (!fullscreen.supported) return;
          e.preventDefault();
          fullscreen.toggle();
        }}
        onPlay={() => {
          setPaused(false);
          onPlayState?.(true);
        }}
        onPause={() => {
          setPaused(true);
          onPlayState?.(false);
          if (!ref.current?.ended) save.current(false);
        }}
        // In a Watch Together room, the room starts it.
        autoPlay={!sync}
        playsInline
        onTimeUpdate={onTimeUpdate}
        onLoadedMetadata={() => {
          loaded.current = true;
          const at = resumeFrom?.() ?? 0;
          if (ref.current && at > 5) {
            ref.current.currentTime = at;
            lastSave.current = at;
            if (resumedAt && Math.abs(at - resumedAt) < 1) {
              setResumeNote(true);
              setTimeout(() => setResumeNote(false), RESUME_NOTE_MS);
            }
          }
        }}
        onPlaying={onStart}
        // Only the video's own errors; a subtitle track failing isn't the stream failing.
        onError={(e) => e.target === e.currentTarget && fail.current()}
        onDurationChange={() => setDuration(ref.current?.duration || 0)}
        onEnded={() => next && autoNext && next.go()}
        className="h-full w-full bg-black"
      >
        {stream.subtitles.map((sub, i) => (
          <track
            key={sub.url}
            kind="subtitles"
            src={sub.url}
            label={sub.label}
            srcLang={sub.lang ?? undefined}
            default={i === 0}
          />
        ))}
      </video>

      {partySync.blocked && (
        <button
          onClick={partySync.unblock}
          className="absolute inset-0 z-10 grid place-items-center bg-black/60 text-lg font-semibold"
        >
          <span className="rounded bg-white px-6 py-3 text-black shadow-lg">
            ▶ {t("together.joinPlayback")}
          </span>
        </button>
      )}

      {resumeNote && resumedAt && (
        <div className="absolute top-4 left-1/2 flex -translate-x-1/2 items-center gap-3 rounded bg-black/75 px-4 py-2 text-sm backdrop-blur">
          {t("player.resumedAt", { time: formatTime(resumedAt) })}
          <button
            onClick={() => {
              if (ref.current) ref.current.currentTime = 0;
              setResumeNote(false);
            }}
            className="rounded bg-white/15 px-2 py-0.5 font-semibold hover:bg-white/25"
          >
            {t("player.startOver")}
          </button>
        </div>
      )}

      {/* No intro times known yet: a plain jump over a typical opening instead. */}
      {!opening && time > 5 && time < SKIP_AHEAD_UNTIL_S && !inCredits && (
        <button
          onClick={() => ref.current && (ref.current.currentTime += SKIP_AHEAD_S)}
          title={t("player.skipAheadInfo")}
          className={`absolute right-8 bottom-24 rounded border border-white/50 bg-black/50 px-4 py-1.5 text-sm font-semibold backdrop-blur transition-opacity hover:bg-white hover:text-black ${idle && !paused ? "opacity-0" : "opacity-100"}`}
        >
          » {formatTime(SKIP_AHEAD_S)}
        </button>
      )}

      {inIntro && (
        <button
          onClick={() => ref.current && (ref.current.currentTime = opening.end_s)}
          className="absolute right-8 bottom-24 rounded border-2 border-white/80 bg-black/60 px-6 py-2.5 text-lg font-semibold tracking-wide backdrop-blur transition-colors hover:bg-white hover:text-black"
        >
          {t("player.skipIntro")}
        </button>
      )}

      {inCredits && next && !creditsDismissed && (
        <NextEpisodeCard
          next={next}
          countdown={autoNext}
          video={ref}
          onDismiss={() => setCreditsDismissed(true)}
        />
      )}
      {inCredits && !next && ending && time < ending.end_s - 0.5 && (
        <button
          onClick={() => ref.current && (ref.current.currentTime = ending.end_s)}
          className="absolute right-8 bottom-24 rounded border-2 border-white/80 bg-black/60 px-6 py-2.5 text-lg font-semibold backdrop-blur hover:bg-white hover:text-black"
        >
          {t("player.skipCredits")}
        </button>
      )}
      <FullscreenButton
        fullscreen={fullscreen}
        className={`top-4 right-4 ${idle && !paused ? "pointer-events-none opacity-0" : ""}`}
      />
    </div>
  );
}

function NextEpisodeCard({
  next,
  countdown,
  video,
  onDismiss,
}: {
  next: NextEpisode;
  countdown: boolean;
  video: React.RefObject<HTMLVideoElement | null>;
  onDismiss: () => void;
}) {
  const { t } = useT();
  const [left, setLeft] = useState(NEXT_COUNTDOWN_S);
  const started = useRef(false);

  useEffect(() => {
    if (!countdown) return;
    // Like Netflix, the countdown only runs while the video plays.
    const timer = setInterval(() => {
      if (video.current && !video.current.paused) setLeft((l) => Math.max(0, l - 0.25));
    }, 250);
    return () => clearInterval(timer);
  }, [countdown, video]);

  useEffect(() => {
    if (countdown && left <= 0 && !started.current) {
      started.current = true;
      next.go();
    }
  }, [countdown, left, next]);

  const progress = countdown ? (1 - left / NEXT_COUNTDOWN_S) * 100 : 0;

  return (
    <div className="absolute right-8 bottom-24 flex flex-col items-end gap-2">
      <button
        onClick={next.go}
        className="relative overflow-hidden rounded bg-white px-6 py-2.5 text-lg font-semibold text-black shadow-lg"
      >
        <span
          aria-hidden
          className="absolute inset-y-0 left-0 bg-neutral-300 transition-[width] duration-200 ease-linear"
          style={{ width: `${progress}%` }}
        />
        <span className="relative">
          ▶ {next.label}
          {countdown && (
            <span className="ml-2 text-sm font-normal">
              {t("player.inSeconds", { s: Math.ceil(left) })}
            </span>
          )}
        </span>
      </button>
      <button
        onClick={onDismiss}
        className="rounded bg-black/60 px-3 py-1 text-sm text-white/80 backdrop-blur hover:text-white"
      >
        {t("player.watchCredits")}
      </button>
    </div>
  );
}
