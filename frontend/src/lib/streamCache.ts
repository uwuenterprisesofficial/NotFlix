/**
 * The browser's copy of a show's stream data (GET /anime/{id}/streams): every episode's sources
 * plus the resolved streams, kept in memory and in localStorage until they expire, so moving to
 * another episode, switching language or reloading the page needs no requests.
 */
import type { Resolved, SourceOption } from "./types";

export type ProviderCoverage = { name: string; status: string; episodes: number[] };
export type StoredResolution = { episode: number; option: string; resolved: Resolved };
export type ShowStreams = {
  providers: ProviderCoverage[];
  scanning: boolean;
  expires_at: string;
  episodes: { episode: number; options: SourceOption[] }[];
  resolutions: StoredResolution[];
};

const PREFIX = "notflix:streams:";
const INDEX_KEY = "notflix:streams";
const MAX_SHOWS = 8; // most recently watched shows kept in localStorage

const memory = new Map<number, ShowStreams | null>();
const listeners = new Set<() => void>();

export const isFresh = (expiresAt: string | null | undefined) =>
  !!expiresAt && Date.parse(expiresAt) > Date.now();

export function subscribeStreams(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** The stored data (possibly expired), or null. Stable between writes. */
export function getShowStreams(animeId: number): ShowStreams | null {
  if (!memory.has(animeId)) {
    let found: ShowStreams | null = null;
    try {
      const raw = localStorage.getItem(PREFIX + animeId);
      found = raw ? JSON.parse(raw) : null;
    } catch {
      found = null;
    }
    memory.set(animeId, found);
  }
  return memory.get(animeId) ?? null;
}

function persist(animeId: number, data: ShowStreams) {
  const save = () => {
    let index: number[] = [];
    try {
      index = JSON.parse(localStorage.getItem(INDEX_KEY) ?? "[]");
    } catch {}
    index = [animeId, ...index.filter((id) => id !== animeId)];
    for (const old of index.slice(MAX_SHOWS)) localStorage.removeItem(PREFIX + old);
    localStorage.setItem(INDEX_KEY, JSON.stringify(index.slice(0, MAX_SHOWS)));
    localStorage.setItem(PREFIX + animeId, JSON.stringify(data));
  };
  try {
    save();
  } catch {
    // Storage full or unavailable: the in-memory copy still serves this visit.
  }
}

function write(animeId: number, data: ShowStreams) {
  memory.set(animeId, data);
  persist(animeId, data);
  for (const listener of listeners) listener();
}

const inflight = new Map<number, Promise<ShowStreams>>();

/** Fetch and store a show's stream data; concurrent callers share one request. */
export function loadShowStreams(animeId: number, episode: number): Promise<ShowStreams> {
  let request = inflight.get(animeId);
  if (!request) {
    request = fetch(`/api/anime/${animeId}/streams?episode=${episode}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: ShowStreams) => {
        write(animeId, data);
        return data;
      })
      .finally(() => inflight.delete(animeId));
    inflight.set(animeId, request);
  }
  return request;
}

/** One provider's options for one episode, fetched because the show data didn't cover it. */
export function saveEpisodeOptions(
  animeId: number,
  provider: string,
  episode: number,
  options: SourceOption[],
) {
  const show = getShowStreams(animeId);
  if (!show) return;
  const others = show.episodes.find((e) => e.episode === episode)?.options ?? [];
  const merged = [...others.filter((o) => o.provider !== provider), ...options];
  const order = show.providers.map((p) => p.name);
  merged.sort((a, b) => order.indexOf(a.provider) - order.indexOf(b.provider));
  write(animeId, {
    ...show,
    providers: show.providers.map((p) =>
      p.name === provider && !p.episodes.includes(episode)
        ? { ...p, episodes: [...p.episodes, episode] }
        : p,
    ),
    episodes: [
      ...show.episodes.filter((e) => e.episode !== episode),
      { episode, options: merged },
    ].sort((a, b) => a.episode - b.episode),
  });
}

export function saveResolution(
  animeId: number,
  episode: number,
  option: string,
  resolved: Resolved,
) {
  const show = getShowStreams(animeId);
  if (!show || !isFresh(resolved.expires_at)) return;
  write(animeId, {
    ...show,
    resolutions: [
      ...show.resolutions.filter(
        (r) => isFresh(r.resolved.expires_at) && !(r.episode === episode && r.option === option),
      ),
      { episode, option, resolved },
    ],
  });
}

export function dropResolution(animeId: number, episode: number, option: string) {
  const show = getShowStreams(animeId);
  if (!show) return;
  write(animeId, {
    ...show,
    resolutions: show.resolutions.filter((r) => !(r.episode === episode && r.option === option)),
  });
}

export function storedResolution(
  show: ShowStreams | null,
  episode: number,
  option: string,
): Resolved | null {
  const found = show?.resolutions.find((r) => r.episode === episode && r.option === option);
  return found && isFresh(found.resolved.expires_at) ? found.resolved : null;
}

/** Drop a show's copy, e.g. after its sources were refreshed or a mapping was corrected. */
export function forgetShowStreams(animeId: number) {
  memory.set(animeId, null);
  try {
    localStorage.removeItem(PREFIX + animeId);
  } catch {}
  for (const listener of listeners) listener();
}
