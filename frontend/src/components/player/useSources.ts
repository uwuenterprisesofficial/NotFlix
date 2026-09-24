import { useEffect, useRef, useState } from "react";
import { LANGUAGE_ORDER } from "@/lib/languages";
import type { Language, Resolved, SourceOption, Stream } from "@/lib/types";
import { useStoredValue } from "./useStoredValue";

type Resolution = { ok: true; resolved: Resolved } | { ok: false; error: string };

// How long to hold out for a direct stream before settling for an embedded player.
const DIRECT_PATIENCE_MS = 8000;

async function resolveOption(animeId: number, episode: number, id: string): Promise<Resolution> {
  try {
    const res = await fetch(
      `/api/anime/${animeId}/episodes/${episode}/resolve?option=${encodeURIComponent(id)}`,
    );
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      return {
        ok: false,
        error: body?.detail ?? `Source failed (${res.status})`,
      };
    }
    const resolved: Resolved = await res.json();
    return resolved.streams.length
      ? { ok: true, resolved }
      : { ok: false, error: "No playable stream from this source" };
  } catch {
    return { ok: false, error: "Network error" };
  }
}

export type Continue = {
  provider: string | null;
  label: string | null;
  server: string | null;
};

/**
 * Loads every provider's source options for an episode in parallel, groups them by language and
 * resolves all of the current language's sources. Without an explicit choice it plays a working
 * direct stream (which NotFlix's own player controls), preferring the provider and server the
 * previous episode used; an embedded player is the fallback when no source has one in time.
 * Direct streams that fail to play are skipped. Once something plays, sources answering later
 * never take over.
 */
export function useSources(
  animeId: number,
  episode: number,
  prefer: Continue = { provider: null, label: null, server: null },
) {
  const [providers, setProviders] = useState<string[] | null>(null);
  const [arrivals, setArrivals] = useState<[string, SourceOption[]][]>([]);
  const [loadError, setLoadError] = useState(false);
  const [resolutions, setResolutions] = useState<Record<string, Resolution>>({});
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [streamChoice, setStreamChoice] = useState<Record<string, string>>({});
  const [failedStreams, setFailedStreams] = useState<Record<string, true>>({});
  const [playingId, setPlayingId] = useState<string | null>(null);
  const [search, setSearch] = useState({ round: 0, patient: true });
  const [preferred, setPreferred] = useStoredValue<Language>("notflix:language", "de-dub");
  const inflight = useRef(new Set<string>());

  useEffect(() => {
    let cancelled = false;
    const arrive = (name: string, found: SourceOption[]) =>
      setArrivals((current) =>
        cancelled || current.some(([n]) => n === name) ? current : [...current, [name, found]],
      );
    fetch("/api/providers")
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((names: string[]) => {
        if (cancelled) return;
        setProviders(names);
        for (const name of names) {
          fetch(
            `/api/anime/${animeId}/episodes/${episode}/sources?provider=${encodeURIComponent(name)}`,
          )
            .then((res) => (res.ok ? res.json() : []))
            .catch(() => [])
            .then((found: SourceOption[]) => arrive(name, found));
        }
      })
      .catch(() => !cancelled && setLoadError(true));
    return () => {
      cancelled = true;
    };
  }, [animeId, episode]);

  const { round } = search;
  useEffect(() => {
    const timer = setTimeout(
      () => setSearch((s) => ({ ...s, patient: false })),
      DIRECT_PATIENCE_MS,
    );
    return () => clearTimeout(timer);
  }, [round]);

  const pending = providers ? providers.length - arrivals.length : null;
  const all = arrivals.flatMap(([, found]) => found);
  const languages = LANGUAGE_ORDER.filter((lang) => all.some((o) => o.language === lang));
  // While providers are still answering, wait for the preferred language instead of falling back.
  const language =
    languages.includes(preferred) || pending !== 0 ? preferred : (languages[0] ?? preferred);
  const candidates = all.filter((o) => o.language === language);

  const resolutionOf = (o: SourceOption): Resolution | undefined =>
    o.resolved ? { ok: true, resolved: o.resolved } : resolutions[o.id];
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
    !arrivals.some(([name]) => name === prefer.provider);
  const stillLooking = pending !== 0 || usable.some((o) => !resolutionOf(o));

  function autoPick(): SourceOption | null {
    // Stay with what plays, unless its direct streams all failed and another source has one.
    const playing = usable.find((o) => o.id === playingId);
    if (playing && (hasDirect(playing) || !usable.some(hasDirect))) return playing;
    if (waitForPreferred) return null;
    const direct = usable.find(hasDirect);
    // The previous episode's source is likely direct again; give it the chance to answer.
    const preferredResolving = usable[0] && rank(usable[0]) < 2 && !resolutionOf(usable[0]);
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

  // Resolve every source of the language at once: the dropdown shows what each one offers, and
  // the first working direct stream doesn't have to wait for sources ahead of it.
  useEffect(() => {
    for (const o of candidates) {
      if (o.resolved || inflight.current.has(o.id)) continue;
      inflight.current.add(o.id);
      resolveOption(animeId, episode, o.id).then((result) =>
        setResolutions((current) => ({ ...current, [o.id]: result })),
      );
    }
  }, [candidates, animeId, episode]);

  let error: string | null = null;
  if (activeResolution && !activeResolution.ok) error = activeResolution.error;
  else if (activeResolution && !streams.length) error = "None of its streams would play";

  return {
    loading: !loadError && pending !== 0,
    loadError,
    languages,
    language,
    setLanguage: (lang: Language) => {
      setPreferred(lang);
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
    /** A direct stream that couldn't be played; the next working one takes its place. */
    failStream: (url: string) => setFailedStreams((f) => ({ ...f, [url]: true })),
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
