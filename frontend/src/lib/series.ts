"use client";

import { useEffect, useState } from "react";
import { useStoredValue } from "@/components/player/useStoredValue";

/** Series from SerienStream: found and played through the series service the desktop app runs
 * on the PC (/series-api, see proxy.ts). They have no MyAnimeList id, so the backend only keeps
 * the user's progress in them (/api/series/...). */

export type SeriesHit = {
  slug: string;
  title: string;
  description: string;
  image: string | null;
};

export type SeriesInfo = {
  slug: string;
  title: string;
  description: string;
  banner: string | null;
  /** The poster (null when the site's results page doesn't show it). */
  cover: string | null;
  yearStart: number;
  yearEnd: number | null;
  genres: string[];
  seasons: number;
  hasMovies: boolean;
};

export type SeriesEpisode = {
  number: number;
  title: string;
  originalTitle: string;
  hosters: string[];
  languages: { audio: string; subtitle: string | null }[];
};

export type SeriesStream = {
  url: string;
  hoster: string;
  audio: string;
  subtitle: string | null;
};

export type SeriesEpisodeStreams = {
  number: number;
  season: number | null;
  title: string;
  streams: SeriesStream[];
};

/** The user's progress in a series, kept by the backend. */
export type SeriesProgress = {
  slug: string;
  title: string;
  image_url: string | null;
  season: number;
  episode: number;
  updated_at: string;
};

export class SeriesError extends Error {
  constructor(public status: number) {
    super(`series service answered ${status}`);
  }
}

export async function seriesGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`/series-api${path}`, { signal });
  if (!res.ok) throw new SeriesError(res.status);
  return res.json() as Promise<T>;
}

export const seriesHref = (slug: string) => `/series/${encodeURIComponent(slug)}`;
export const seriesWatchHref = (slug: string, season: number, episode: number) =>
  `${seriesHref(slug)}/watch/${season}/${episode}`;

/** Season 0 is the series' movies. */
export const seasonLabel = (season: number) => (season === 0 ? "Movies" : `S${season}`);

// One check per page load: the series service is there in the desktop app only.
let availability: Promise<boolean> | null = null;

function checkAvailable(): Promise<boolean> {
  availability ??= fetch("/series-api/health")
    .then((res) => res.ok)
    .catch(() => false);
  return availability;
}

/** Whether the series service runs (null while that's being checked). */
export function useSeriesAvailable(): boolean | null {
  const [available, setAvailable] = useState<boolean | null>(null);
  useEffect(() => {
    let live = true;
    void checkAvailable().then((ok) => live && setAvailable(ok));
    return () => {
      live = false;
    };
  }, []);
  return available;
}

/** Include series in the search (default off). */
export const useIncludeSeries = () => useStoredValue<"on" | "off">("notflix:series-search", "off");

/** Remember the episode the user is on (a signed-out visitor has no progress; that's fine). */
export async function saveSeriesProgress(
  info: Pick<SeriesInfo, "slug" | "title" | "banner" | "cover">,
  season: number,
  episode: number,
): Promise<void> {
  await fetch(`/api/series/${encodeURIComponent(info.slug)}/progress`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title: info.title, image_url: info.cover ?? info.banner, season, episode }),
  }).catch(() => {});
}

export async function clearSeriesProgress(slug: string): Promise<void> {
  await fetch(`/api/series/${encodeURIComponent(slug)}/progress`, { method: "DELETE" }).catch(
    () => {},
  );
}

export async function loadSeriesProgress(): Promise<SeriesProgress[]> {
  try {
    const res = await fetch("/api/series/progress");
    return res.ok ? ((await res.json()) as SeriesProgress[]) : [];
  } catch {
    return [];
  }
}

const infos = new Map<string, Promise<SeriesInfo>>();

/** A series' details, asked once per page load. */
export function loadSeriesInfo(slug: string): Promise<SeriesInfo> {
  let info = infos.get(slug);
  if (!info) {
    info = seriesGet<SeriesInfo>(`/series/${encodeURIComponent(slug)}`);
    infos.set(slug, info);
    info.catch(() => infos.delete(slug));
  }
  return info;
}

// --- Searching, mixed in with the anime results ---

const TYPING_PAUSE_MS = 500;

type HitsState = { q: string; hits: SeriesHit[]; failed: boolean };

/** SerienStream's results for a search text (when `enabled`): the hits, and whether the
 * answer for this very text is still on its way. */
export function useSeriesHits(q: string, enabled: boolean) {
  const available = useSeriesAvailable();
  const [include] = useIncludeSeries();
  const [state, setState] = useState<HitsState>({ q: "", hits: [], failed: false });
  const active = enabled && available === true && include === "on" && q.length > 0;

  useEffect(() => {
    if (!active) return;
    const abort = new AbortController();
    const timer = setTimeout(() => {
      seriesGet<SeriesHit[]>(`/search?q=${encodeURIComponent(q)}`, abort.signal)
        .then((hits) => setState({ q, hits, failed: false }))
        .catch(() => !abort.signal.aborted && setState({ q, hits: [], failed: true }));
    }, TYPING_PAUSE_MS);
    return () => {
      clearTimeout(timer);
      abort.abort();
    };
  }, [active, q]);

  const current = state.q === q;
  return {
    active,
    hits: active && current ? state.hits : [],
    pending: active && !current,
    failed: active && current && state.failed,
  };
}

const normalize = (text: string) =>
  text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();

/** How well titles match the search text (0-100, the best of them): the whole title, then
 * titles starting with it, then ones containing it, then ones sharing words with it. */
export function matchScore(query: string, titles: (string | null | undefined)[]): number {
  const wanted = normalize(query);
  if (!wanted) return 0;
  const words = wanted.split(" ");
  let best = 0;
  for (const title of titles) {
    const text = normalize(title ?? "");
    if (!text) continue;
    let score: number;
    if (text === wanted) score = 100;
    else if (text.startsWith(wanted)) score = 90 - Math.min(10, (text.length - wanted.length) / 3);
    else if (text.includes(wanted)) score = 65;
    else {
      const have = text.split(" ");
      const shared: number[] = words.map((w) =>
        have.includes(w) ? 1 : have.some((h) => h.startsWith(w)) ? 0.7 : text.includes(w) ? 0.4 : 0,
      );
      score = 50 * (shared.reduce((a, b) => a + b, 0) / words.length);
    }
    best = Math.max(best, score);
  }
  return best;
}

export type Mixed<A> = { kind: "anime"; anime: A } | { kind: "series"; hit: SeriesHit };

/** The anime (in their order) with the series put in where they match the search better than
 * the anime after them: one list, best matches first. */
export function mixResults<A>(
  query: string,
  anime: A[],
  titlesOf: (a: A) => (string | null | undefined)[],
  hits: SeriesHit[],
): Mixed<A>[] {
  const series = hits
    .map((hit, i) => ({ hit, i, score: matchScore(query, [hit.title]) }))
    .sort((a, b) => b.score - a.score || a.i - b.i);
  const mixed: Mixed<A>[] = [];
  let next = 0;
  for (const a of anime) {
    const score = matchScore(query, titlesOf(a));
    while (next < series.length && series[next].score > score) {
      mixed.push({ kind: "series", hit: series[next++].hit });
    }
    mixed.push({ kind: "anime", anime: a });
  }
  while (next < series.length) mixed.push({ kind: "series", hit: series[next++].hit });
  return mixed;
}
