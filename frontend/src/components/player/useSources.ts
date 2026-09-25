import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import {
  dropResolution,
  getShowStreams,
  isFresh,
  type ShowStreams,
  saveEpisodeOptions,
  loadShowStreams,
  saveResolution,
  storedResolution,
  subscribeStreams,
} from "@/lib/streamCache";
import type { Language, Resolved, SourceOption, Stream } from "@/lib/types";
import { useStreamLanguage } from "@/lib/streamLanguage";

type Resolution = { ok: true; resolved: Resolved } | { ok: false; error: string };

// How long to hold out for a direct stream before settling for an embedded player.
const DIRECT_PATIENCE_MS = 8000;
// Resolve the next episode's source once this one has been playing for a moment.
const PREFETCH_AFTER_MS = 10_000;
// Links older than this may have expired early when they fail; younger ones are just broken.
const STALE_LINKS_MS = 10 * 60_000;

async function resolveOption(
  animeId: number,
  episode: number,
  id: string,
  fresh = false,
): Promise<Resolution> {
  try {
    const params = new URLSearchParams({ option: id });
    if (fresh) params.set("fresh", "true");
    const res = await fetch(`/api/anime/${animeId}/episodes/${episode}/resolve?${params}`);
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      return { ok: false, error: body?.detail ?? `Source failed (${res.status})` };
    }
    const resolved: Resolved = await res.json();
    if (!resolved.streams.length)
      return { ok: false, error: "No playable stream from this source" };
    saveResolution(animeId, episode, id, resolved);
    return { ok: true, resolved };
  } catch {
    return { ok: false, error: "Network error" };
  }
}

/** Providers that haven't looked at this episode yet (and haven't failed outright). */
function unsettled(show: ShowStreams, episode: number) {
  return show.providers
    .filter((p) => p.status !== "failed" && !p.episodes.includes(episode))
    .map((p) => p.name);
}

export type Continue = { provider: string | null; label: string | null; server: string | null };

/**
 * An episode's sources, grouped by language, from the show's stream data that the browser keeps
 * (one request per show while it's fresh; none when moving between episodes, switching
 * language or reloading). Without an explicit choice it plays a working direct stream (which
 * NotFlix's own player controls), preferring the provider and server the previous episode used;
 * an embedded player is the fallback when no source has one in time. Direct streams that fail
 * to play are skipped. Once something plays, sources answering later never take over.
 */
export function useSources(
  animeId: number,
  episode: number,
  prefer: Continue = { provider: null, label: null, server: null },
) {
  const show = useSyncExternalStore(
    subscribeStreams,
    () => getShowStreams(animeId),
    () => null,
  );
  const [loadError, setLoadError] = useState(false);
  // Providers whose live lookup for this episode failed; not waited for any longer.
  const [gaveUp, setGaveUp] = useState<string[]>([]);
  const [resolutions, setResolutions] = useState<Record<string, Resolution>>({});
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [streamChoice, setStreamChoice] = useState<Record<string, string>>({});
  const [failedStreams, setFailedStreams] = useState<Record<string, true>>({});
  const [refreshed, setRefreshed] = useState<Record<string, true>>({});
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [search, setSearch] = useState({ round: 0, patient: true });
  const { order, chosen: chosenLanguage, choose } = useStreamLanguage(animeId);
  const inflight = useRef(new Set<string>());
  const prefetched = useRef(false);

  // The show's stream data: the stored copy while it's fresh, else one request. Providers that
  // haven't covered this episode yet are asked for just this episode.
  const [reload, setReload] = useState(0);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    (async () => {
      let data = getShowStreams(animeId);
      if (!data || !isFresh(data.expires_at)) {
        try {
          data = await loadShowStreams(animeId, episode);
        } catch {
          if (!cancelled && !data) setLoadError(true);
          if (!data) return;
        }
        if (cancelled) return;
      }
      // Fetched mid-scan: fetch again once the scan should be done, so later episodes find
      // complete data.
      if (data.scanning)
        timer = setTimeout(
          () => setReload((r) => r + 1),
          Math.max(1000, Date.parse(data.expires_at) - Date.now() + 500),
        );
      for (const name of unsettled(data, episode)) {
        fetch(
          `/api/anime/${animeId}/episodes/${episode}/sources?provider=${encodeURIComponent(name)}`,
        )
          .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
          .then((found: SourceOption[]) => {
            if (cancelled) return;
            // An empty answer may be a provider outage; only keep real finds.
            if (found.length) saveEpisodeOptions(animeId, name, episode, found);
            else setGaveUp((g) => [...g, name]);
          })
          .catch(() => !cancelled && setGaveUp((g) => [...g, name]));
      }
    })();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [animeId, episode, reload]);

  const { round } = search;
  useEffect(() => {
    const timer = setTimeout(
      () => setSearch((s) => ({ ...s, patient: false })),
      DIRECT_PATIENCE_MS,
    );
    return () => clearTimeout(timer);
  }, [round]);

  const providers = show?.providers.map((p) => p.name) ?? null;
  const waiting = show ? unsettled(show, episode).filter((name) => !gaveUp.includes(name)) : null;
  const pending = waiting?.length ?? null;
  const all = show?.episodes.find((e) => e.episode === episode)?.options ?? [];
  const languages = order.filter((lang) => all.some((o) => o.language === lang));
  // The language picked for this show, else the first of the preference order (dub, then sub
  // in the UI's language, then the other) this episode has. While providers are still
  // answering, a better language the show has elsewhere is waited for instead of falling back.
  const showHas = (lang: Language) =>
    show?.episodes.some((e) => e.options.some((o) => o.language === lang)) ?? false;
  const language =
    chosenLanguage && (languages.includes(chosenLanguage) || pending !== 0 || !languages.length)
      ? chosenLanguage
      : (order.find((l) => languages.includes(l) || (pending !== 0 && showHas(l))) ??
        languages[0] ??
        chosenLanguage ??
        order[0]);
  const candidates = all.filter((o) => o.language === language);

  const resolutionOf = (o: SourceOption): Resolution | undefined => {
    if (o.resolved) return { ok: true, resolved: o.resolved };
    if (o.id in resolutions) return resolutions[o.id];
    const stored = storedResolution(show, episode, o.id);
    return stored ? { ok: true, resolved: stored } : undefined;
  };
  const streamsOf = (o: SourceOption): Stream[] => {
    const r = resolutionOf(o);
    return r?.ok ? r.resolved.streams : [];
  };
  const working = (s: Stream) => !failedStreams[s.url];
  const hasWorking = (o: SourceOption) => streamsOf(o).some(working);
  const hasDirect = (o: SourceOption) =>
    streamsOf(o).some((s) => s.kind === "direct" && working(s));
  const failed = (o: SourceOption) => {
    const r = resolutionOf(o);
    return !!r && (!r.ok || !hasWorking(o));
  };

  // Continue with the provider the previous episode played from (e.g. after "Next Episode"),
  // waiting for its sources rather than starting with whichever provider answers first.
  const rank = (o: SourceOption) =>
    o.provider !== prefer.provider ? 2 : o.label === prefer.label ? 0 : 1;
  const usable = candidates.filter((o) => !failed(o)).sort((a, b) => rank(a) - rank(b));
  const waitForPreferred =
    !!prefer.provider &&
    !!providers?.includes(prefer.provider) &&
    !!waiting?.includes(prefer.provider);
  const stillLooking = pending !== 0 || usable.some((o) => !resolutionOf(o));
  // The previous episode's source is likely direct again; give it the chance to answer first.
  const preferredResolving = !!usable[0] && rank(usable[0]) < 2 && !resolutionOf(usable[0]);

  function autoPick(): SourceOption | null {
    // Stay with what plays, unless its direct streams all failed and another source has one.
    const playing = usable.find((o) => o.id === playingId);
    if (playing && (hasDirect(playing) || !resolutionOf(playing) || !usable.some(hasDirect)))
      return playing;
    if (waitForPreferred) return null;
    const direct = usable.find(hasDirect);
    if (direct && !preferredResolving) return direct;
    if (stillLooking && search.patient) return null;
    return usable.find(hasWorking) ?? null;
  }

  const chosen = candidates.find((o) => o.id === chosenId) ?? null;
  const active = chosen ?? autoPick();
  const activeResolution = active ? resolutionOf(active) : undefined;

  const streams = active ? streamsOf(active).filter(working) : [];
  const streamRank = (s: Stream) =>
    (s.kind === "direct" ? 0 : 2) + (s.label === prefer.server ? 0 : 1);
  const stream =
    streams.find((s) => active && s.url === streamChoice[active.id]) ??
    [...streams].sort((a, b) => streamRank(a) - streamRank(b))[0] ??
    null;

  // Resolve only what's needed: the active source; while searching for a direct stream, the
  // previous episode's source first and then the rest of the language; everything once the
  // stream menu is opened. Stored resolutions make most of these free.
  let wanted: SourceOption[] = [];
  if (showAll) wanted = candidates;
  else if (active) wanted = [active];
  else if (waitForPreferred) wanted = [];
  else if (preferredResolving) wanted = [usable[0]];
  else wanted = candidates;
  const resolveKey = wanted
    .filter((o) => !resolutionOf(o))
    .map((o) => o.id)
    .join(" ");
  useEffect(() => {
    for (const id of resolveKey ? resolveKey.split(" ") : []) {
      if (inflight.current.has(id)) continue;
      inflight.current.add(id);
      resolveOption(animeId, episode, id).then((result) => {
        inflight.current.delete(id);
        setResolutions((current) => ({ ...current, [id]: result }));
      });
    }
  }, [resolveKey, animeId, episode]);

  // Once this episode plays, resolve the next episode's matching source, so "Next Episode"
  // starts right away with the same stream.
  const playingOption = candidates.find((o) => o.id === playingId);
  const nextOptions = show?.episodes.find((e) => e.episode === episode + 1)?.options ?? [];
  const nextMatch = playingOption
    ? (nextOptions.find(
        (o) => o.provider === playingOption.provider && o.label === playingOption.label,
      ) ??
      nextOptions.find(
        (o) => o.provider === playingOption.provider && o.language === playingOption.language,
      ))
    : undefined;
  const nextId =
    nextMatch && !nextMatch.resolved && !storedResolution(show, episode + 1, nextMatch.id)
      ? nextMatch.id
      : null;
  useEffect(() => {
    if (!nextId || prefetched.current) return;
    const timer = setTimeout(() => {
      prefetched.current = true;
      void resolveOption(animeId, episode + 1, nextId);
    }, PREFETCH_AFTER_MS);
    return () => clearTimeout(timer);
  }, [nextId, animeId, episode]);

  let error: string | null = null;
  if (activeResolution && !activeResolution.ok) error = activeResolution.error;
  else if (activeResolution && !streams.length) error = "None of its streams would play";

  /** A direct stream that couldn't be played. Stored links may have expired early: when they
   * aren't brand new, the source's links are fetched fresh once; otherwise the next working
   * stream takes over. */
  function failStream(url: string) {
    const owner = candidates.find((o) => streamsOf(o).some((s) => s.url === url));
    const r = owner && resolutionOf(owner);
    const fetchedAt = r?.ok && r.resolved.resolved_at ? Date.parse(r.resolved.resolved_at) : 0;
    if (
      owner &&
      !owner.resolved &&
      !refreshed[owner.id] &&
      Date.now() - fetchedAt > STALE_LINKS_MS
    ) {
      const id = owner.id;
      setRefreshed((r) => ({ ...r, [id]: true }));
      dropResolution(animeId, episode, id);
      setResolutions((current) => {
        const next = { ...current };
        delete next[id];
        return next;
      });
      inflight.current.add(id);
      resolveOption(animeId, episode, id, true).then((result) => {
        inflight.current.delete(id);
        setResolutions((current) => ({ ...current, [id]: result }));
      });
      return;
    }
    setFailedStreams((f) => ({ ...f, [url]: true }));
  }

  return {
    loading: !loadError && pending !== 0,
    loadError,
    languages,
    language,
    countIn: (lang: Language) => all.filter((o) => o.language === lang).length,
    setLanguage: (lang: Language) => {
      choose(lang);
      setChosenId(null);
      setPlayingId(null);
      setSearch((s) => ({ round: s.round + 1, patient: true }));
    },
    candidates,
    active,
    stream,
    streamsOf,
    resolutionOf,
    /** Play this source, and this one of its streams if given. */
    choose: (id: string, url?: string) => {
      setChosenId(id);
      if (url) setStreamChoice((c) => ({ ...c, [id]: url }));
    },
    failStream,
    /** Load every source of the language, e.g. to list them all in the stream menu. */
    showAll: () => setShowAll(true),
    /** The active source started playing: keep it even if a "better" one answers later. */
    started: () => {
      if (active) setPlayingId(active.id);
    },
    streamFailed: (s: Stream) => !working(s),
    searching: !active && !loadError && !waitForPreferred && stillLooking && search.patient,
    resolving: active !== null && activeResolution === undefined,
    resolved: activeResolution?.ok ? activeResolution.resolved : null,
    error,
  };
}
