"use client";

import type Hls from "hls.js";
import { useEffect, useRef, useState } from "react";
import type { SkipSegment, Stream } from "@/lib/types";

const LABELS: Record<SkipSegment["kind"], string> = {
  opening: "Skip Intro",
  ending: "Skip Outro",
};

function useStream(ref: React.RefObject<HTMLVideoElement | null>, url: string, isHls: boolean) {
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
      hls.loadSource(url);
      hls.attachMedia(video);
    });
    return () => {
      cancelled = true;
      hls?.destroy();
    };
  }, [ref, url, isHls]);
}

/** A <video> we fully control, so intro/outro skipping works (unlike cross-origin iframes). */
export function DirectVideo({
  stream,
  segments,
  autoSkip,
  nextEpisodeLabel,
  onSkipEnding,
  onNearEnd,
}: {
  stream: Stream;
  segments: SkipSegment[];
  autoSkip: boolean;
  nextEpisodeLabel: string | null;
  onSkipEnding: (() => void) | null;
  onNearEnd: () => void;
}) {
  const ref = useRef<HTMLVideoElement>(null);
  const autoSkipped = useRef(new Set<SkipSegment["kind"]>());
  const [active, setActive] = useState<SkipSegment | null>(null);
  useStream(ref, stream.url, stream.format === "hls");

  function skip(segment: SkipSegment) {
    if (segment.kind === "ending" && onSkipEnding) onSkipEnding();
    else if (ref.current) ref.current.currentTime = segment.end_s;
  }

  function onTimeUpdate() {
    const video = ref.current;
    if (!video) return;
    const t = video.currentTime;
    const current = segments.find((s) => t >= s.start_s && t < s.end_s - 0.5) ?? null;
    if (current?.kind !== active?.kind) setActive(current);

    // Auto-skip each segment once; seeking back into it afterwards plays it normally.
    if (current && autoSkip && !autoSkipped.current.has(current.kind)) {
      autoSkipped.current.add(current.kind);
      skip(current);
    }

    const ending = segments.find((s) => s.kind === "ending");
    const nearEnd = ending ? t >= ending.start_s : video.duration && t >= video.duration * 0.9;
    if (nearEnd) onNearEnd();
  }

  const label =
    active?.kind === "ending" && onSkipEnding && nextEpisodeLabel
      ? nextEpisodeLabel
      : active && LABELS[active.kind];

  return (
    <>
      <video
        ref={ref}
        controls
        autoPlay
        playsInline
        onTimeUpdate={onTimeUpdate}
        onEnded={() => onSkipEnding?.()}
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
      {active && (
        <button
          onClick={() => skip(active)}
          className="absolute right-6 bottom-20 rounded border border-white/70 bg-black/70 px-5 py-2 font-semibold backdrop-blur hover:bg-white hover:text-black"
        >
          {label}
        </button>
      )}
    </>
  );
}
