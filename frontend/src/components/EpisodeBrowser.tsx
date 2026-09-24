"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LANGUAGE_LABELS, LANGUAGE_ORDER, LANGUAGE_SHORT, PROVIDER_LABELS } from "@/lib/languages";
import type { Availability, Language } from "@/lib/types";
import { useStoredValue } from "./player/useStoredValue";

const POLL_MS = 3000;
export const SCAN_FINISHED_EVENT = "notflix:scan-finished";
/** Dispatch after changing what providers should find (e.g. a mapping) to rescan. */
export const SOURCES_CHANGED_EVENT = "notflix:sources-changed";
// Airing shows have no episode count on MAL yet; show at least this many.
const UNKNOWN_EPISODE_COUNT = 12;

type Status = "available" | "other-language" | "none" | "checking" | "unknown";

/**
 * Episode grid with per-language availability. Opening the page makes the backend scan every
 * provider in the background; the grid fills in from the cache and polls while scans run.
 */
export function EpisodeBrowser({
  animeId,
  numEpisodes,
  watched,
  signedIn,
}: {
  animeId: number;
  numEpisodes: number | null;
  watched: number;
  signedIn: boolean;
}) {
  const [data, setData] = useState<Availability | null>(null);
  const [failed, setFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [language, setLanguage] = useStoredValue<Language>("notflix:language", "de-dub");

  const scanning = data?.scanning ?? true;
  useEffect(() => {
    if (!scanning) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = () =>
      fetch(`/api/anime/${animeId}/availability`)
        .then((res) => (res.ok ? res.json() : Promise.reject(res.status)))
        .then((next: Availability) => {
          if (cancelled) return;
          setData(next);
          if (next.scanning) timer = setTimeout(load, POLL_MS);
          // Scans can create provider mappings (e.g. AniWorld); let other panels refresh.
          else window.dispatchEvent(new Event(SCAN_FINISHED_EVENT));
        })
        .catch(() => !cancelled && setFailed(true));
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [animeId, scanning]);

  useEffect(() => {
    // Marking the data as scanning restarts polling, and the first poll starts the scan.
    const rescan = () => setData((current) => current && { ...current, scanning: true });
    window.addEventListener(SOURCES_CHANGED_EVENT, rescan);
    return () => window.removeEventListener(SOURCES_CHANGED_EVENT, rescan);
  }, []);

  async function refresh() {
    setRefreshing(true);
    const res = await fetch(`/api/anime/${animeId}/availability/refresh`, { method: "POST" });
    if (res.ok) setData(await res.json());
    setRefreshing(false);
  }

  const languagesByEpisode = new Map(data?.episodes.map((e) => [e.episode, e.languages]));
  const checked = new Set(data?.checked);
  const lastAvailable = Math.max(0, ...languagesByEpisode.keys());
  const count = numEpisodes ?? Math.max(UNKNOWN_EPISODE_COUNT, watched + 1, lastAvailable);
  const episodes = Array.from({ length: count }, (_, i) => i + 1);

  const perLanguage = new Map<Language, number>();
  for (const langs of languagesByEpisode.values())
    for (const lang of langs) perLanguage.set(lang, (perLanguage.get(lang) ?? 0) + 1);
  const shownLanguages = LANGUAGE_ORDER.filter(
    (lang) => lang !== "unknown" || perLanguage.has("unknown"),
  );

  function status(ep: number): Status {
    const langs = languagesByEpisode.get(ep) ?? [];
    if (langs.includes(language)) return "available";
    if (langs.length) return "other-language";
    if (checked.has(ep)) return "none";
    return data?.scanning ? "checking" : "unknown";
  }

  const running = data?.scans.filter((s) => s.status === "running") ?? [];
  const broken = data?.scans.filter((s) => s.status === "failed") ?? [];
  const noneCount = episodes.filter((ep) => status(ep) === "none").length;

  return (
    <section className="mt-12">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <h2 className="mr-2 text-xl font-semibold">Episodes</h2>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Language">
          {shownLanguages.map((lang) => (
            <button
              key={lang}
              role="radio"
              aria-checked={lang === language}
              onClick={() => setLanguage(lang)}
              className={`rounded-full px-3 py-1 text-sm font-semibold ${
                lang === language
                  ? "bg-white text-black"
                  : perLanguage.has(lang)
                    ? "bg-surface-raised hover:bg-neutral-700"
                    : "bg-surface-raised text-muted hover:bg-neutral-700"
              }`}
            >
              {LANGUAGE_LABELS[lang]}
              <span className="ml-1.5 text-xs opacity-60">{perLanguage.get(lang) ?? 0}</span>
            </button>
          ))}
        </div>
        {signedIn && (
          <button
            onClick={refresh}
            disabled={refreshing || scanning}
            className="ml-auto rounded px-3 py-1 text-sm text-muted hover:text-white disabled:opacity-50"
          >
            ↻ Refresh sources
          </button>
        )}
      </div>

      <div className="mb-3 min-h-5 text-sm text-muted" aria-live="polite">
        {failed && "Couldn’t load episode availability."}
        {running.length > 0 &&
          `Looking for episodes on ${running.map((s) => PROVIDER_LABELS[s.provider] ?? s.provider).join(", ")}…`}
        {broken.length > 0 && (
          <span className="block text-amber-400/80">
            {broken.map((s) => PROVIDER_LABELS[s.provider] ?? s.provider).join(", ")} couldn’t be
            reached; retrying later.
          </span>
        )}
        {!scanning && noneCount > 0 && (
          <span className="block">
            {noneCount} episode{noneCount === 1 ? "" : "s"} without any stream.
          </span>
        )}
      </div>

      <div className="grid grid-cols-4 gap-2 sm:grid-cols-8 lg:grid-cols-12">
        {episodes.map((ep) => (
          <EpisodeTile
            key={ep}
            animeId={animeId}
            episode={ep}
            watched={ep <= watched}
            status={status(ep)}
            languages={languagesByEpisode.get(ep) ?? []}
          />
        ))}
      </div>

      <p className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
        <span>
          <span className="mr-1 inline-block size-2 rounded-full bg-green-500" />
          {LANGUAGE_LABELS[language]}
        </span>
        <span>
          <span className="mr-1 inline-block size-2 rounded-full bg-amber-400" />
          Other languages only
        </span>
        <span>
          <span className="mr-1 inline-block size-2 rounded-full bg-red-500" />
          No stream
        </span>
      </p>
    </section>
  );
}

const TILE: Record<Status, string> = {
  available: "bg-neutral-700 hover:bg-brand",
  "other-language": "bg-neutral-800 text-neutral-300 hover:bg-neutral-700",
  none: "bg-neutral-900 text-neutral-600",
  checking: "animate-pulse bg-neutral-800 text-neutral-400",
  unknown: "bg-neutral-800 text-neutral-400 hover:bg-neutral-700",
};

const DOT: Partial<Record<Status, string>> = {
  available: "bg-green-500",
  "other-language": "bg-amber-400",
  none: "bg-red-500",
};

function EpisodeTile({
  animeId,
  episode,
  watched,
  status,
  languages,
}: {
  animeId: number;
  episode: number;
  watched: boolean;
  status: Status;
  languages: Language[];
}) {
  const title =
    status === "none"
      ? "No stream found for this episode"
      : status === "checking"
        ? "Looking for streams…"
        : languages.map((l) => LANGUAGE_LABELS[l]).join(", ") || undefined;
  const content = (
    <>
      {DOT[status] && (
        <span className={`absolute top-1.5 right-1.5 size-1.5 rounded-full ${DOT[status]}`} />
      )}
      <span className={`${watched ? "opacity-60" : ""} ${status === "none" ? "line-through" : ""}`}>
        {watched ? "✓ " : ""}
        {episode}
      </span>
      {status === "other-language" && (
        <span className="block text-[10px] leading-tight font-normal text-amber-300/80">
          {languages.map((l) => LANGUAGE_SHORT[l]).join(" · ")}
        </span>
      )}
      {status === "none" && (
        <span className="block text-[10px] leading-tight font-normal">No stream</span>
      )}
    </>
  );
  const className = `relative block rounded py-3 text-center text-sm font-semibold transition-colors ${TILE[status]}`;

  if (status === "none") {
    return (
      <span className={className} title={title} aria-label={`Episode ${episode}: no stream`}>
        {content}
      </span>
    );
  }
  return (
    <Link href={`/watch/${animeId}/${episode}`} className={className} title={title}>
      {content}
    </Link>
  );
}
