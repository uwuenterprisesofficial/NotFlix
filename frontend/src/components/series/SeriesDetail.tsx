"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  clearSeriesProgress,
  loadSeriesInfo,
  loadSeriesProgress,
  seriesGet,
  SeriesError,
  type SeriesEpisode,
  type SeriesInfo,
  type SeriesProgress,
  seriesWatchHref,
  useSeriesAvailable,
} from "@/lib/series";
import { useT } from "../I18nProvider";

type Load<T> = { key: string; value: T | null; error: number | null };

/** A series: its text, seasons and episodes (all from the series service on this PC). */
export function SeriesDetail({ slug }: { slug: string }) {
  const { t } = useT();
  const available = useSeriesAvailable();
  const [info, setInfo] = useState<Load<SeriesInfo>>({ key: "", value: null, error: null });
  const [progress, setProgress] = useState<SeriesProgress | null>(null);
  const [chosen, setChosen] = useState<number | null>(null);
  const [episodes, setEpisodes] = useState<Load<SeriesEpisode[]>>({
    key: "",
    value: null,
    error: null,
  });

  useEffect(() => {
    if (!available) return;
    let live = true;
    loadSeriesInfo(slug)
      .then((value) => live && setInfo({ key: slug, value, error: null }))
      .catch((e) => live && setInfo({ key: slug, value: null, error: e instanceof SeriesError ? e.status : 0 }));
    void loadSeriesProgress().then((all) => live && setProgress(all.find((p) => p.slug === slug) ?? null));
    return () => {
      live = false;
    };
  }, [available, slug]);

  const series = info.key === slug ? info.value : null;
  // The season the user is in, else the first.
  const first = series && series.seasons < 1 && series.hasMovies ? 0 : 1;
  const season = chosen ?? progress?.season ?? first;
  const episodesKey = `${slug}/${season}`;

  useEffect(() => {
    if (!series) return;
    const abort = new AbortController();
    seriesGet<SeriesEpisode[]>(`/series/${encodeURIComponent(slug)}/seasons/${season}`, abort.signal)
      .then((value) => setEpisodes({ key: episodesKey, value, error: null }))
      .catch((e) => !abort.signal.aborted && setEpisodes({ key: episodesKey, value: null, error: e instanceof SeriesError ? e.status : 0 }));
    return () => abort.abort();
  }, [series, slug, season, episodesKey]);

  if (available === false) {
    return <p className="mt-6 text-muted">{t("series.unavailable")}</p>;
  }
  if (info.key === slug && info.error !== null) {
    return (
      <p className="mt-6 text-muted">
        {info.error === 404 ? t("series.notFound") : t("series.loadFailed")}
      </p>
    );
  }
  if (!series) return <div className="mt-6 h-64 animate-pulse rounded-lg bg-surface-raised" />;

  const poster = series.cover ?? series.banner;
  const seasons = [
    ...(series.hasMovies ? [0] : []),
    ...Array.from({ length: series.seasons }, (_, i) => i + 1),
  ];
  const list = episodes.key === episodesKey ? episodes : null;
  const episodeLabel = (season: number, episode: number) =>
    t(season === 0 ? "series.movie" : "series.episode", { episode });

  return (
    <div className="mt-4 flex flex-col gap-8 md:flex-row">
      {poster && (
        // eslint-disable-next-line @next/next/no-img-element -- the site's own picture
        <img
          src={poster}
          alt={series.title}
          referrerPolicy="no-referrer"
          className="aspect-[2/3] w-48 shrink-0 self-start rounded-lg object-cover"
        />
      )}
      <div className="min-w-0 flex-1">
        <h1 className="text-3xl font-black">{series.title}</h1>
        <p className="mt-1 text-sm text-muted">
          {series.yearStart}
          {series.yearEnd && series.yearEnd !== series.yearStart ? `–${series.yearEnd}` : ""}
          {series.genres.length > 0 && ` · ${series.genres.join(", ")}`}
        </p>
        {series.description && <p className="mt-4 max-w-3xl">{series.description}</p>}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          {progress ? (
            <>
              <Link
                href={seriesWatchHref(slug, progress.season, progress.episode)}
                className="rounded bg-brand px-5 py-2 font-semibold hover:bg-brand-dark"
              >
                ▶ {t("series.continue", { episode: `S${progress.season} E${progress.episode}` })}
              </Link>
              <button
                onClick={() => {
                  void clearSeriesProgress(slug);
                  setProgress(null);
                }}
                className="rounded bg-surface-raised px-4 py-2 text-sm hover:bg-white/10"
              >
                {t("series.removeProgress")}
              </button>
            </>
          ) : (
            list?.value?.[0] && (
              <Link
                href={seriesWatchHref(slug, season, list.value[0].number)}
                className="rounded bg-brand px-5 py-2 font-semibold hover:bg-brand-dark"
              >
                ▶ {t("series.start")}
              </Link>
            )
          )}
        </div>

        <h2 className="mt-8 text-lg font-semibold">{t("series.seasons")}</h2>
        <div className="mt-2 flex flex-wrap gap-2">
          {seasons.map((s) => (
            <button
              key={s}
              onClick={() => setChosen(s)}
              aria-pressed={s === season}
              className={`rounded px-3 py-1.5 text-sm ${s === season ? "bg-white text-black" : "bg-surface-raised hover:bg-white/10"}`}
            >
              {s === 0 ? t("series.movies") : s}
            </button>
          ))}
        </div>

        <ul className="mt-4 divide-y divide-white/10 rounded-lg bg-surface-raised">
          {list?.value?.map((e) => {
            const current = progress?.season === season && progress.episode === e.number;
            return (
              <li key={e.number}>
                <Link
                  href={seriesWatchHref(slug, season, e.number)}
                  className={`flex items-baseline gap-3 px-4 py-3 hover:bg-white/10 ${current ? "bg-white/10" : ""}`}
                >
                  <span className="w-8 shrink-0 text-muted">{e.number}</span>
                  <span className="min-w-0 flex-1 truncate">
                    {e.title || e.originalTitle || episodeLabel(season, e.number)}
                  </span>
                  {current && <span className="text-xs text-brand">▶</span>}
                  <span className="hidden text-xs text-muted sm:inline">{e.hosters.join(" · ")}</span>
                </Link>
              </li>
            );
          })}
        </ul>
        {!list && <div className="mt-4 h-32 animate-pulse rounded-lg bg-surface-raised" />}
        {list?.error !== null && list && <p className="mt-4 text-muted">{t("series.loadFailed")}</p>}
        {list?.value?.length === 0 && <p className="mt-4 text-muted">{t("series.noEpisodes")}</p>}
      </div>
    </div>
  );
}
