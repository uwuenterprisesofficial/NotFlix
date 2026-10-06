"use client";

import type Hls from "hls.js";
import { useEffect, useRef, useState } from "react";
import { getShowStreams, reportStream, saveEpisodeOptions, storedResolution } from "@/lib/streamCache";
import type { Language, SourceOption, Stream } from "@/lib/types";
import type { Continue } from "./useSources";
import { resolveOption } from "./useSources";

// From this long before the end, the next episode is made ready.
export const PRELOAD_BEFORE_END_S = 5 * 60;
// A stream that hasn't loaded its first data by then counts as not working.
const LOAD_TIMEOUT_MS = 20_000;
// How many of the next episode's sources are tried.
const MAX_TRIES = 4;

type Preloaded = { element: HTMLVideoElement; hls?: Hls };

/** Load a direct stream into a hidden video until it has its first data: it works, and its
 * start is in the browser's cache for when the episode begins. */
function preload(stream: Stream, signal: AbortSignal): Promise<Preloaded> {
  return new Promise((resolve, reject) => {
    const video = document.createElement("video");
    video.muted = true;
    video.preload = "auto";
    let hls: Hls | undefined;
    const fail = () => {
      clearTimeout(timer);
      hls?.destroy();
      video.removeAttribute("src");
      video.load();
      reject(new Error("unplayable"));
    };
    const timer = setTimeout(fail, LOAD_TIMEOUT_MS);
    signal.addEventListener("abort", fail, { once: true });
    video.addEventListener(
      "loadeddata",
      () => {
        clearTimeout(timer);
        resolve({ element: video, hls });
      },
      { once: true },
    );
    video.addEventListener("error", fail, { once: true });
    if (stream.format !== "hls" || video.canPlayType("application/vnd.apple.mpegurl")) {
      video.src = stream.url;
    } else {
      import("hls.js").then(({ default: HlsClass }) => {
        if (signal.aborted || !HlsClass.isSupported()) return fail();
        hls = new HlsClass({ maxBufferLength: 60 });
        hls.on(HlsClass.Events.ERROR, (_e, data) => data.fatal && fail());
        hls.loadSource(stream.url);
        hls.attachMedia(video);
      }, fail);
    }
  });
}

/** The next episode's sources in the current language: the same provider and source as now
 * first, then the same provider, then the rest. */
async function nextOptions(
  animeId: number,
  episode: number,
  language: Language,
  current: Continue,
): Promise<SourceOption[]> {
  let options = getShowStreams(animeId)?.episodes.find((e) => e.episode === episode)?.options;
  if (!options?.length) {
    // Not scanned yet: ask for this episode.
    const res = await fetch(`/api/anime/${animeId}/episodes/${episode}/sources`).catch(() => null);
    options = res?.ok ? ((await res.json()) as SourceOption[]) : [];
    for (const provider of new Set(options.map((o) => o.provider))) {
      saveEpisodeOptions(
        animeId,
        provider,
        episode,
        options.filter((o) => o.provider === provider),
      );
    }
  }
  const rank = (o: SourceOption) =>
    o.provider !== current.provider ? 2 : o.label === current.label ? 0 : 1;
  return options.filter((o) => o.language === language).sort((a, b) => rank(a) - rank(b));
}

/**
 * Near the end of an episode (the last five minutes), the next one is made ready: its source
 * is looked up and resolved, and its direct stream is loaded into a hidden video, so it is
 * known to play and its beginning is buffered when "Next Episode" comes. Sources whose streams
 * don't load are skipped (and remembered as broken). Returns what the next episode should
 * start with, once found.
 */
export function usePreloadNext({
  animeId,
  episode,
  enabled,
  language,
  current,
}: {
  animeId: number;
  episode: number;
  enabled: boolean;
  language: Language | null;
  current: Continue;
}) {
  const [near, setNear] = useState(false);
  const [ready, setReady] = useState<Continue | null>(null);
  const kept = useRef<Preloaded | null>(null);
  const currentRef = useRef(current);
  useEffect(() => {
    currentRef.current = current;
  });

  useEffect(() => {
    if (!near || !enabled || !language) return;
    const abort = new AbortController();
    const next = episode + 1;
    (async () => {
      const options = await nextOptions(animeId, next, language, currentRef.current);
      for (const option of options.slice(0, MAX_TRIES)) {
        if (abort.signal.aborted) return;
        const stored = storedResolution(getShowStreams(animeId), next, option.id);
        const resolution = stored
          ? { ok: true as const, resolved: stored }
          : await resolveOption(animeId, next, option.id);
        if (!resolution.ok) continue;
        const direct = resolution.resolved.streams
          .filter((s) => s.kind === "direct")
          .sort(
            (a, b) =>
              Number(b.label === currentRef.current.server) -
              Number(a.label === currentRef.current.server),
          );
        for (const stream of direct) {
          try {
            kept.current = await preload(stream, abort.signal);
          } catch {
            if (abort.signal.aborted) return;
            reportStream(animeId, { episode: next, option: option.id, stream: stream.label }, true);
            continue;
          }
          setReady({ provider: option.provider, label: option.label, server: stream.label });
          return;
        }
      }
    })();
    return () => abort.abort();
  }, [near, enabled, language, animeId, episode]);

  // The hidden video goes when this episode's page does (its data stays in the cache).
  useEffect(
    () => () => {
      kept.current?.hls?.destroy();
      kept.current?.element.removeAttribute("src");
    },
    [],
  );

  return {
    /** What the next episode should start with: a source and server that were seen to load. */
    ready,
    /** The current position: from five minutes before the end, the next episode is prepared. */
    onPosition: (position: number, duration: number) => {
      if (!near && duration > 0 && duration - position <= PRELOAD_BEFORE_END_S) setNear(true);
    },
  };
}
