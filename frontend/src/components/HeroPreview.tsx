"use client";

import { useEffect, useRef, useState } from "react";
import { OTHER_PREVIEW_EVENT, otherPreviewsPlaying } from "@/lib/previewFocus";
import { useAudioPreference, useHeroPreview, usePreviewStart } from "@/lib/preferences";
import { languageOrder } from "@/lib/streamLanguage";
import type { Episode, SourceOption, Stream } from "@/lib/types";
import { useT } from "./I18nProvider";
import { useStream } from "./player/DirectVideo";
import { resolveOption } from "./player/useSources";

// How much of the episode plays when the preview starts at its beginning.
const PREVIEW_LENGTH_S = 120;
// Sources tried for a direct stream before giving up (the poster simply stays).
const MAX_SOURCES = 4;

type Clip = { stream: Stream; from: number; until: number };

/** Direct streams of an episode, best language first (as the player would pick). */
async function directStreams(
  animeId: number,
  episode: number,
  order: string[],
  cancelled: () => boolean,
): Promise<Stream[]> {
  const res = await fetch(`/api/anime/${animeId}/episodes/${episode}/sources`).catch(() => null);
  const options: SourceOption[] = res?.ok ? await res.json() : [];
  const rank = (o: SourceOption) => {
    const i = order.indexOf(o.language);
    return i === -1 ? order.length : i;
  };
  const found: Stream[] = [];
  for (const option of [...options].sort((a, b) => rank(a) - rank(b)).slice(0, MAX_SOURCES)) {
    if (cancelled()) return [];
    const resolution = option.resolved
      ? { ok: true as const, resolved: option.resolved }
      : await resolveOption(animeId, episode, option.id);
    if (resolution.ok) found.push(...resolution.resolved.streams.filter((s) => s.kind === "direct"));
    if (found.length) break;
  }
  return found;
}

/**
 * The home page's preview: the show at the top plays muted behind its title once its episode
 * has loaded (the blurred poster shows until then, and again after). It starts at the
 * episode's beginning, or at its opening when that's known (AniSkip or NotFlix's detection),
 * as chosen in the settings. Paused while scrolled away or in another tab.
 */
export function HeroPreview({ animeId, episode }: { animeId: number; episode: number }) {
  const { t, lang } = useT();
  const [enabled] = useHeroPreview();
  const [startAt] = usePreviewStart();
  const [audio] = useAudioPreference();
  const [streams, setStreams] = useState<Stream[]>([]);
  const [index, setIndex] = useState(0);
  const [range, setRange] = useState<{ from: number; until: number } | null>(null);
  const [playing, setPlaying] = useState(false);
  const [done, setDone] = useState(false);
  const [muted, setMuted] = useState(true);
  const ref = useRef<HTMLVideoElement>(null);
  const fail = useRef(() => {});
  useEffect(() => {
    fail.current = () => setIndex((i) => i + 1);
  });

  useEffect(() => {
    if (enabled !== "on") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let cancelled = false;
    (async () => {
      const [found, info] = await Promise.all([
        directStreams(animeId, episode, languageOrder(lang, audio), () => cancelled),
        startAt === "opening"
          ? fetch(`/api/anime/${animeId}/episodes/${episode}`)
              .then((r) => (r.ok ? (r.json() as Promise<Episode>) : null))
              .catch(() => null)
          : Promise.resolve(null),
      ]);
      if (cancelled) return;
      const opening = info?.skip_segments.find((s) => s.kind === "opening");
      setRange(
        opening
          ? { from: opening.start_s, until: opening.end_s }
          : { from: 0, until: PREVIEW_LENGTH_S },
      );
      setStreams(found);
    })();
    return () => {
      cancelled = true;
    };
  }, [enabled, animeId, episode, startAt, lang, audio]);

  const stream = streams[index] ?? null;
  return stream && range && !done ? (
    <Clip
      clip={{ stream, ...range }}
      videoRef={ref}
      fail={fail}
      playing={playing}
      muted={muted}
      onPlaying={() => setPlaying(true)}
      onEnd={() => {
        setPlaying(false);
        setDone(true);
      }}
      toggleMute={() => setMuted((m) => !m)}
      labels={{ mute: t("hero.mute"), unmute: t("hero.unmute") }}
    />
  ) : null;
}

function Clip({
  clip,
  videoRef,
  fail,
  playing,
  muted,
  onPlaying,
  onEnd,
  toggleMute,
  labels,
}: {
  clip: Clip;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  fail: React.RefObject<() => void>;
  playing: boolean;
  muted: boolean;
  onPlaying: () => void;
  onEnd: () => void;
  toggleMute: () => void;
  labels: { mute: string; unmute: string };
}) {
  useStream(videoRef, clip.stream.url, clip.stream.format === "hls", fail);

  // Only while it can be seen and nothing else previews: paused when scrolled away, in a
  // background tab, or while a hover card's preview plays.
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    let inView = true;
    const update = () => {
      if (!playing) return;
      if (inView && document.visibilityState === "visible" && !otherPreviewsPlaying()) {
        void video.play().catch(() => {});
      } else video.pause();
    };
    const observer = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      update();
    });
    observer.observe(video);
    document.addEventListener("visibilitychange", update);
    window.addEventListener(OTHER_PREVIEW_EVENT, update);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", update);
      window.removeEventListener(OTHER_PREVIEW_EVENT, update);
    };
  }, [videoRef, playing]);

  return (
    <>
      <video
        ref={videoRef}
        muted={muted}
        playsInline
        preload="auto"
        aria-hidden
        onLoadedMetadata={(e) => {
          const video = e.currentTarget;
          if (clip.from > 0 && clip.from < (video.duration || Infinity)) video.currentTime = clip.from;
          void video.play().catch(() => {});
        }}
        onPlaying={onPlaying}
        onTimeUpdate={(e) => e.currentTarget.currentTime >= clip.until && onEnd()}
        onEnded={onEnd}
        onError={() => fail.current()}
        className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-1000 ${playing ? "opacity-60" : "opacity-0"}`}
      />
      {playing && (
        <button
          onClick={toggleMute}
          aria-label={muted ? labels.unmute : labels.mute}
          title={muted ? labels.unmute : labels.mute}
          className="absolute right-4 bottom-24 z-10 grid size-10 place-items-center rounded-full border border-white/60 bg-black/40 text-lg hover:bg-black/60 md:right-12"
        >
          {muted ? "🔇" : "🔊"}
        </button>
      )}
    </>
  );
}
