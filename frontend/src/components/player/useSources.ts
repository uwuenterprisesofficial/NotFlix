import { useEffect, useRef, useState } from "react";
import { LANGUAGE_ORDER } from "@/lib/languages";
import type { Language, Resolved, SourceOption } from "@/lib/types";
import { useStoredValue } from "./useStoredValue";

type Resolution = { ok: true; resolved: Resolved } | { ok: false; error: string };

async function resolveOption(animeId: number, episode: number, id: string): Promise<Resolution> {
  try {
    const res = await fetch(
      `/api/anime/${animeId}/episodes/${episode}/resolve?option=${encodeURIComponent(id)}`,
    );
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      return { ok: false, error: body?.detail ?? `Source failed (${res.status})` };
    }
    const resolved: Resolved = await res.json();
    return resolved.streams.length
      ? { ok: true, resolved }
      : { ok: false, error: "No playable stream from this source" };
  } catch {
    return { ok: false, error: "Network error" };
  }
}

/**
 * Loads every provider's source options for an episode in parallel, groups them by language and
 * resolves the active one on demand. Without an explicit choice, the first option that doesn't
 * fail is used. Options are kept in arrival order so a slow provider answering late can't take
 * over from the source already playing.
 */
export function useSources(
  animeId: number,
  episode: number,
  prefer: { provider: string | null; label: string | null } = { provider: null, label: null },
) {
  const [providers, setProviders] = useState<string[] | null>(null);
  const [arrivals, setArrivals] = useState<[string, SourceOption[]][]>([]);
  const [loadError, setLoadError] = useState(false);
  const [resolutions, setResolutions] = useState<Record<string, Resolution>>({});
  const [chosenId, setChosenId] = useState<string | null>(null);
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

  const pending = providers ? providers.length - arrivals.length : null;
  const all = arrivals.flatMap(([, found]) => found);
  const languages = LANGUAGE_ORDER.filter((lang) => all.some((o) => o.language === lang));
  // While providers are still answering, wait for the preferred language instead of falling back.
  const language =
    languages.includes(preferred) || pending !== 0 ? preferred : (languages[0] ?? preferred);
  const candidates = all.filter((o) => o.language === language);

  const resolutionOf = (o: SourceOption): Resolution | undefined =>
    o.resolved ? { ok: true, resolved: o.resolved } : resolutions[o.id];
  const chosen = candidates.find((o) => o.id === chosenId);
  const usable = candidates.filter((o) => resolutionOf(o)?.ok !== false);
  // Continue with the provider the previous episode played from (e.g. after "Next Episode"),
  // waiting for its sources rather than starting with whichever provider answers first.
  const preferredArrived = arrivals.some(([name]) => name === prefer.provider);
  const waitForPreferred =
    !!prefer.provider && !!providers?.includes(prefer.provider) && !preferredArrived;
  const fromPreferred = usable.filter((o) => o.provider === prefer.provider);
  const continued = fromPreferred.find((o) => o.label === prefer.label) ?? fromPreferred[0];
  const active = chosen ?? continued ?? (waitForPreferred ? null : usable[0]) ?? null;
  const activeResolution = active ? resolutionOf(active) : undefined;

  useEffect(() => {
    if (!active || active.resolved || inflight.current.has(active.id)) return;
    inflight.current.add(active.id);
    resolveOption(animeId, episode, active.id).then((result) =>
      setResolutions((current) => ({ ...current, [active.id]: result })),
    );
  }, [active, animeId, episode]);

  return {
    loading: !loadError && pending !== 0,
    loadError,
    languages,
    language,
    setLanguage: (lang: Language) => {
      setPreferred(lang);
      setChosenId(null);
    },
    candidates,
    active,
    choose: setChosenId,
    failed: (o: SourceOption) => resolutionOf(o)?.ok === false,
    resolving: active !== null && activeResolution === undefined,
    resolved: activeResolution?.ok ? activeResolution.resolved : null,
    error: activeResolution && !activeResolution.ok ? activeResolution.error : null,
  };
}
