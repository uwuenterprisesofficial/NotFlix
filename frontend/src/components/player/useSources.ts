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
 * Loads every source option for an episode, groups them by language and resolves the active one
 * on demand. Without an explicit choice, the first option that doesn't fail is used.
 */
export function useSources(animeId: number, episode: number) {
  const [options, setOptions] = useState<SourceOption[] | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [resolutions, setResolutions] = useState<Record<string, Resolution>>({});
  const [chosenId, setChosenId] = useState<string | null>(null);
  const [preferred, setPreferred] = useStoredValue<Language>("notflix:language", "de-dub");
  const inflight = useRef(new Set<string>());

  useEffect(() => {
    fetch(`/api/anime/${animeId}/episodes/${episode}/sources`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
      .then((found: SourceOption[]) => setOptions(found))
      .catch(() => setLoadError(true));
  }, [animeId, episode]);

  const all = options ?? [];
  const languages = LANGUAGE_ORDER.filter((lang) => all.some((o) => o.language === lang));
  const language = languages.includes(preferred) ? preferred : (languages[0] ?? preferred);
  const candidates = all.filter((o) => o.language === language);

  const resolutionOf = (o: SourceOption): Resolution | undefined =>
    o.resolved ? { ok: true, resolved: o.resolved } : resolutions[o.id];
  const chosen = candidates.find((o) => o.id === chosenId);
  const active = chosen ?? candidates.find((o) => resolutionOf(o)?.ok !== false) ?? null;
  const activeResolution = active ? resolutionOf(active) : undefined;

  useEffect(() => {
    if (!active || active.resolved || inflight.current.has(active.id)) return;
    inflight.current.add(active.id);
    resolveOption(animeId, episode, active.id).then((result) =>
      setResolutions((current) => ({ ...current, [active.id]: result })),
    );
  }, [active, animeId, episode]);

  return {
    loading: options === null && !loadError,
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
