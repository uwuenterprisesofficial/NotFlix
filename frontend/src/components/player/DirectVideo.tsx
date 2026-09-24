"use client";

import type Hls from "hls.js";
import { useEffect, useRef, useState } from "react";
import type { SkipSegment, Stream } from "@/lib/types";

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
// A stream that hasn't loaded anything by then counts as broken.
const LOAD_TIMEOUT_MS = 20_000;
// Without detected credits, the "Next Episode" card shows this long before the end.
const FALLBACK_CREDITS_S = 30;

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
}) {
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
  useStream(ref, stream.url, stream.format === "hls", fail);

  useEffect(() => {
    const timer = setTimeout(() => loaded.current || fail.current(), LOAD_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, []);

  const opening = segments.find((s) => s.kind === "opening");
  const ending = segments.find((s) => s.kind === "ending");
  const inIntro = !!opening && time >= opening.start_s && time < opening.end_s - 0.5;
  const creditsAt = ending?.start_s ?? (duration ? duration - FALLBACK_CREDITS_S : Infinity);
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
    if (t >= (ending?.start_s ?? video.duration * 0.9)) onNearEnd();
  }

  return (
    <>
      <video
        ref={ref}
        controls
        autoPlay
        playsInline
        onTimeUpdate={onTimeUpdate}
        onLoadedMetadata={() => {
          loaded.current = true;
          const at = resumeFrom?.() ?? 0;
          if (ref.current && at > 5) ref.current.currentTime = at;
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

      {inIntro && (
        <button
          onClick={() => ref.current && (ref.current.currentTime = opening.end_s)}
          className="absolute right-8 bottom-24 rounded border-2 border-white/80 bg-black/60 px-6 py-2.5 text-lg font-semibold tracking-wide backdrop-blur transition-colors hover:bg-white hover:text-black"
        >
          Skip Intro
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
          Skip Credits
        </button>
      )}
    </>
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
          {countdown && <span className="ml-2 text-sm font-normal">in {Math.ceil(left)}s</span>}
        </span>
      </button>
      <button
        onClick={onDismiss}
        className="rounded bg-black/60 px-3 py-1 text-sm text-white/80 backdrop-blur hover:text-white"
      >
        Watch credits
      </button>
    </div>
  );
}
