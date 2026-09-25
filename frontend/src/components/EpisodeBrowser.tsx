"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { LOCALE, type T } from "@/lib/i18n";
import { PROVIDER_LABELS } from "@/lib/languages";
import { forgetShowStreams } from "@/lib/streamCache";
import { pickLanguage, useStreamLanguage } from "@/lib/streamLanguage";
import type { Availability, Language } from "@/lib/types";
import { useNow } from "@/lib/useNow";
import { useT } from "./I18nProvider";
import { LanguageFlag } from "./LanguageFlag";
import { Dropdown } from "./player/Dropdown";

const POLL_MS = 3000;
export const SCAN_FINISHED_EVENT = "notflix:scan-finished";
/** Dispatch after changing what providers should find (e.g. a mapping) to rescan. */
export const SOURCES_CHANGED_EVENT = "notflix:sources-changed";
// Airing shows have no episode count on MAL yet; show at least this many.
const UNKNOWN_EPISODE_COUNT = 12;

type Status = "available" | "other-language" | "none" | "checking" | "unknown" | "upcoming";

/**
 * Episode grid with per-language availability. Opening the page makes the backend scan every
 * provider in the background; the grid fills in from the cache and polls while scans run.
 */
export function EpisodeBrowser({
  animeId,
  numEpisodes,
  watched,
  signedIn,
  aired = null,
  nextAt = null,
}: {
  animeId: number;
  numEpisodes: number | null;
  watched: number;
  signedIn: boolean;
  /** Episodes aired so far (null: no limit known); later ones aren't looked for. */
  aired?: number | null;
  /** When the next episode airs. */
  nextAt?: string | null;
}) {
  const [data, setData] = useState<Availability | null>(null);
  const [failed, setFailed] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const { t } = useT();
  const { order, chosen, choose } = useStreamLanguage(animeId);

  // Nothing has aired: there's nothing to look for.
  const nothingAired = aired === 0;
  const scanning = !nothingAired && (data?.scanning ?? true);
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
    const rescan = () => {
      forgetShowStreams(animeId); // the player's copy is outdated too
      setData((current) => current && { ...current, scanning: true });
    };
    window.addEventListener(SOURCES_CHANGED_EVENT, rescan);
    return () => window.removeEventListener(SOURCES_CHANGED_EVENT, rescan);
  }, [animeId]);

  async function refresh() {
    forgetShowStreams(animeId);
    setRefreshing(true);
    const res = await fetch(`/api/anime/${animeId}/availability/refresh`, { method: "POST" });
    if (res.ok) setData(await res.json());
    setRefreshing(false);
  }

  const languagesByEpisode = new Map(data?.episodes.map((e) => [e.episode, e.languages]));
  const checked = new Set(data?.checked);
  const lastAvailable = Math.max(0, ...languagesByEpisode.keys());
  const count =
    numEpisodes ??
    Math.max(UNKNOWN_EPISODE_COUNT, watched + 1, lastAvailable, aired !== null ? aired + 1 : 0);
  const episodes = Array.from({ length: count }, (_, i) => i + 1);

  const perLanguage = new Map<Language, number>();
  for (const langs of languagesByEpisode.values())
    for (const lang of langs) perLanguage.set(lang, (perLanguage.get(lang) ?? 0) + 1);
  const shownLanguages = order.filter((lang) => lang !== "unknown" || perLanguage.has("unknown"));
  // Until the scan finds something, the best language counts as picked.
  const language = pickLanguage(order, perLanguage.keys(), chosen);

  function status(ep: number): Status {
    if (aired !== null && ep > aired) return "upcoming";
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
        <h2 className="mr-2 text-xl font-semibold">{t("episodes.title")}</h2>
        <Dropdown
          align="left"
          className="w-64"
          label={`${t("episodes.language")}: ${t(`lang.${language}`)}`}
          button={
            <>
              <LanguageFlag language={language} />
              <span className="truncate font-semibold">{t(`lang.${language}`)}</span>
              <span className="text-xs text-muted">{perLanguage.get(language) ?? 0}</span>
            </>
          }
        >
          {(close) =>
            shownLanguages.map((lang) => {
              const current = lang === language;
              const count = perLanguage.get(lang) ?? 0;
              return (
                <button
                  key={lang}
                  role="menuitemradio"
                  aria-checked={current}
                  onClick={() => {
                    choose(lang);
                    close();
                  }}
                  className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left ${current ? "bg-white/10" : "hover:bg-white/5"} ${count ? "" : "text-muted"}`}
                >
                  <span aria-hidden className="w-3 text-xs">
                    {current ? "✓" : ""}
                  </span>
                  <LanguageFlag language={lang} />
                  <span className="flex-1 truncate">{t(`lang.${lang}`)}</span>
                  <span className="text-xs text-muted">{t("anime.episodes", { count })}</span>
                </button>
              );
            })
          }
        </Dropdown>
        {signedIn && (
          <button
            onClick={refresh}
            disabled={refreshing || scanning}
            className="ml-auto rounded px-3 py-1 text-sm text-muted hover:text-white disabled:opacity-50"
          >
            {t("episodes.refresh")}
          </button>
        )}
      </div>

      <div className="mb-3 min-h-5 text-sm text-muted" aria-live="polite">
        {nothingAired && t("airing.notAired")}
        {failed && t("episodes.loadFailed")}
        {running.length > 0 && t("episodes.looking", { providers: providerNames(running) })}
        {broken.length > 0 && (
          <span className="block text-amber-400/80">
            {t("episodes.unreachable", { providers: providerNames(broken) })}
          </span>
        )}
        {!scanning && noneCount > 0 && (
          <span className="block">{t("episodes.withoutStream", { count: noneCount })}</span>
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
            t={t}
            airsAt={aired !== null && ep === aired + 1 ? nextAt : null}
          />
        ))}
      </div>

      <p className="mt-3 flex flex-wrap gap-4 text-xs text-muted">
        <span>
          <span className="mr-1 inline-block size-2 rounded-full bg-green-500" />
          {t(`lang.${language}`)}
        </span>
        <span>
          <span className="mr-1 inline-block size-2 rounded-full bg-amber-400" />
          {t("episodes.otherOnly")}
        </span>
        <span>
          <span className="mr-1 inline-block size-2 rounded-full bg-red-500" />
          {t("episodes.noStream")}
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
  upcoming: "border border-dashed border-white/15 text-neutral-500",
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
  t,
  airsAt,
}: {
  animeId: number;
  episode: number;
  watched: boolean;
  status: Status;
  languages: Language[];
  t: T;
  airsAt: string | null;
}) {
  const title =
    status === "upcoming"
      ? t("airing.upcoming")
      : status === "none"
        ? t("episodes.noStreamFound")
        : status === "checking"
          ? t("episodes.lookingStreams")
          : languages.map((l) => t(`lang.${l}`)).join(", ") || undefined;
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
          {languages.map((l) => t(`langShort.${l}`)).join(" · ")}
        </span>
      )}
      {status === "none" && (
        <span className="block text-[10px] leading-tight font-normal">
          {t("episodes.noStream")}
        </span>
      )}
      {status === "upcoming" && airsAt && (
        <span className="block text-[10px] leading-tight font-normal">
          <AirDay at={airsAt} />
        </span>
      )}
    </>
  );
  const className = `relative block rounded py-3 text-center text-sm font-semibold transition-colors ${TILE[status]}`;

  if (status === "none" || status === "upcoming") {
    return (
      <span
        className={className}
        title={title}
        aria-label={
          status === "upcoming"
            ? `${t("player.episodeTitle", { episode })}: ${t("airing.upcoming")}`
            : t("episodes.noStreamLabel", { episode })
        }
      >
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

function providerNames(scans: { provider: string }[]): string {
  return scans.map((s) => PROVIDER_LABELS[s.provider] ?? s.provider).join(", ");
}

/** "Sat 27" in the viewer's time zone (browser only). */
function AirDay({ at }: { at: string }) {
  const { lang } = useT();
  const now = useNow();
  if (now === null) return null;
  return <>{new Date(at).toLocaleDateString(LOCALE[lang], { weekday: "short", day: "numeric" })}</>;
}
