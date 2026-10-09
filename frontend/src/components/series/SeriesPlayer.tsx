"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useAudioPreference } from "@/lib/preferences";
import type { Stream } from "@/lib/types";
import { DirectVideo } from "../player/DirectVideo";
import { usePlayerFrame } from "../player/PlayerFrame";
import { useHeadingSlot } from "./SeriesWatchLayout";
import { useStoredValue } from "../player/useStoredValue";
import {
  clearSeriesProgress,
  loadSeriesInfo,
  saveSeriesProgress,
  seriesGet,
  seriesHref,
  type SeriesEpisode,
  type SeriesEpisodeStreams,
  type SeriesInfo,
  type SeriesStream,
  seriesWatchHref,
  useSeriesAvailable,
} from "@/lib/series";
import { useT } from "../I18nProvider";

type Lang = "en" | "de";
const LANGUAGE_NAME = { en: "English", de: "German" } as const;

/** Which stream to start with: the dub in the UI's language, or the original audio with
 * subtitles in it (lower is better). */
function rank(s: SeriesStream, lang: Lang, preference: "dub" | "sub"): number {
  const mine = LANGUAGE_NAME[lang];
  const dub = s.audio === mine && !s.subtitle;
  const sub = s.audio !== mine && s.subtitle === mine;
  if (preference === "dub") return dub ? 0 : sub ? 1 : s.audio === mine ? 2 : 3;
  return sub ? 0 : dub ? 1 : 3;
}

// Hosters the series service can resolve to the video's own address.
const RESOLVABLE = ["VOE", "Streamtape", "Doodstream", "Vidoza"];

/** The video's own address for a hoster stream (null while it's looked up). */
type Direct = { key: string; stream: Stream | null };

type Load = { key: string; episode: SeriesEpisodeStreams | null; failed: boolean };
type Season = { key: string; episodes: SeriesEpisode[] | null };

/** One episode of a series, in the hoster's own player. The backend remembers the episode, so
 * the series shows up under Continue Watching. */
export function SeriesPlayer({
  slug,
  season,
  episode,
}: {
  slug: string;
  season: number;
  episode: number;
}) {
  const { t, lang } = useT();
  const router = useRouter();
  const available = useSeriesAvailable();
  const [preference] = useAudioPreference();
  const [info, setInfo] = useState<SeriesInfo | null>(null);
  const [load, setLoad] = useState<Load>({ key: "", episode: null, failed: false });
  const [picked, setPicked] = useState<{ key: string; index: number } | null>(null);
  const [siblings, setSiblings] = useState<Season>({ key: "", episodes: null });
  const [autoNext, setAutoNext] = useStoredValue<"0" | "1">("notflix:autonext", "1");
  const [direct, setDirect] = useState<Direct>({ key: "", stream: null });
  // Streams whose video address didn't play: the hoster's own player takes over for them.
  const [broken, setBroken] = useState<string[]>([]);
  // The box the video plays in and the title above it live in the watch layout, which stays
  // mounted from one episode to the next, so fullscreen carries over (as with anime).
  const frame = usePlayerFrame();
  const headingSlot = useHeadingSlot();
  const key = `${slug}/${season}/${episode}`;
  const seasonKey = `${slug}/${season}`;

  useEffect(() => {
    if (!available) return;
    let live = true;
    void loadSeriesInfo(slug)
      .then((value) => {
        if (!live) return;
        setInfo(value);
        // Opening an episode is the progress: it's what Continue Watching comes back to.
        void saveSeriesProgress(value, season, episode);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [available, slug, season, episode]);

  useEffect(() => {
    if (!available) return;
    const abort = new AbortController();
    seriesGet<SeriesEpisodeStreams>(
      `/series/${encodeURIComponent(slug)}/seasons/${season}/episodes/${episode}`,
      abort.signal,
    )
      .then((value) => setLoad({ key, episode: value, failed: false }))
      .catch(() => !abort.signal.aborted && setLoad({ key, episode: null, failed: true }));
    return () => abort.abort();
  }, [available, slug, season, episode, key]);

  const wanted = streamsOf(load, key, lang, preference)[picked?.key === key ? picked.index : 0] ?? null;
  const wantedUrl = wanted?.url ?? null;
  const wantedHoster = wanted?.hoster ?? "";
  useEffect(() => {
    if (!wantedUrl || !RESOLVABLE.includes(wantedHoster)) return;
    const abort = new AbortController();
    seriesGet<{ url: string }>(
      `/resolve?url=${encodeURIComponent(wantedUrl)}&hoster=${encodeURIComponent(wantedHoster)}`,
      abort.signal,
    )
      .then(({ url }) =>
        setDirect({
          key: wantedUrl,
          stream: {
            kind: "direct",
            url,
            label: wantedHoster,
            format: /\.m3u8(\?|$)/.test(url) ? "hls" : "file",
            subtitles: [],
          },
        }),
      )
      .catch(() => !abort.signal.aborted && setDirect({ key: wantedUrl, stream: null }));
    return () => abort.abort();
  }, [wantedUrl, wantedHoster]);

  useEffect(() => {
    if (!available) return;
    const abort = new AbortController();
    seriesGet<SeriesEpisode[]>(`/series/${encodeURIComponent(slug)}/seasons/${season}`, abort.signal)
      .then((episodes) => setSiblings({ key: seasonKey, episodes }))
      .catch(() => {});
    return () => abort.abort();
  }, [available, slug, season, seasonKey]);

  const back = (
    <Link href={seriesHref(slug)} className="text-muted hover:text-white">
      ‹ {info?.title ?? slug}
    </Link>
  );
  const heading = (
    <div className="mb-4 flex items-baseline gap-3">
      {back}
      <h1 className="text-xl font-semibold">
        {season > 0 && `S${season} · `}
        {t(season === 0 ? "series.movie" : "series.episode", { episode })}
        {load.key === key && load.episode?.title && (
          <span className="ml-2 font-normal text-muted">{load.episode.title}</span>
        )}
      </h1>
    </div>
  );

  if (available === false) {
    return (
      <>
        {headingSlot && createPortal(heading, headingSlot)}
        <p className="text-muted">{t("series.unavailable")}</p>
      </>
    );
  }

  const current = load.key === key ? load : null;
  const streams = streamsOf(load, key, lang, preference);
  const index = picked?.key === key ? picked.index : 0;
  const stream = streams[index] ?? null;
  // Which player: the video itself, the hoster's, or none yet (the address is being looked up).
  const lookedUp = !!stream && (direct.key === stream.url || !RESOLVABLE.includes(stream.hoster));
  const own = lookedUp && direct.key === stream?.url ? direct.stream : null;
  const useOwn = !!stream && !!own && !broken.includes(stream.url);

  // The neighbouring episodes: within the season, then into the next season.
  const numbers = siblings.key === seasonKey ? (siblings.episodes ?? []).map((e) => e.number) : [];
  const previous = numbers.filter((n) => n < episode).at(-1);
  const next = numbers.find((n) => n > episode);
  const nextHref =
    next !== undefined
      ? seriesWatchHref(slug, season, next)
      : numbers.length && info && season > 0 && season < info.seasons
        ? seriesWatchHref(slug, season + 1, 1)
        : null;
  const last = numbers.length > 0 && next === undefined && !nextHref;

  const audioName = (audio: string) =>
    t(`series.audio.${audio in LANGUAGE_NAME_KEYS ? audio : "Unknown"}` as "series.audio.Unknown");

  return (
    <>
      {headingSlot && createPortal(heading, headingSlot)}
      {frame &&
        createPortal(
          <>
            {stream && own && useOwn && (
              <DirectVideo
                key={own.url}
                stream={own}
                segments={[]}
                autoSkip={false}
                autoNext={autoNext === "1"}
                next={nextHref ? { label: t("series.next"), go: () => router.push(nextHref) } : null}
                onNearEnd={() => {}}
                onFail={() => setBroken((b) => [...b, stream.url])}
              />
            )}
            {stream && lookedUp && !useOwn && (
              <iframe
                key={stream.url}
                src={stream.url}
                title={t("series.episode", { episode })}
                // No sandbox: hosters detect it and refuse to play.
                allow="autoplay; fullscreen; encrypted-media; picture-in-picture"
                allowFullScreen
                className="h-full w-full border-0"
              />
            )}
            {(!stream || !lookedUp) && (
              <p className="grid h-full place-items-center p-4 text-center text-muted">
                {stream || !current
                  ? t("series.stream") + "…"
                  : current.failed
                    ? t("series.streamsFailed")
                    : t("series.noStreams")}
              </p>
            )}
          </>,
          frame,
        )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        {streams.length > 0 && (
          <select
            aria-label={t("series.stream")}
            value={index}
            onChange={(e) => setPicked({ key, index: Number(e.target.value) })}
            className="rounded border border-white/20 bg-surface-raised px-3 py-2 text-sm"
          >
            {streams.map((s, i) => (
              <option key={s.url} value={i}>
                {s.hoster} · {audioName(s.audio)}
                {s.subtitle ? ` + ${t("series.subtitles", { language: audioName(s.subtitle) })}` : ""}
              </option>
            ))}
          </select>
        )}
        {previous !== undefined && (
          <Link
            href={seriesWatchHref(slug, season, previous)}
            className="rounded bg-surface-raised px-4 py-2 text-sm hover:bg-white/10"
          >
            {t("series.previous")}
          </Link>
        )}
        {nextHref && (
          <Link href={nextHref} className="rounded bg-brand px-4 py-2 text-sm font-semibold hover:bg-brand-dark">
            {t("series.next")}
          </Link>
        )}
        {last && (
          <button
            onClick={() => {
              void clearSeriesProgress(slug).then(() => router.push(seriesHref(slug)));
            }}
            className="rounded bg-surface-raised px-4 py-2 text-sm hover:bg-white/10"
          >
            {t("series.finished")}
          </button>
        )}
      </div>
      <label className="mt-3 flex w-fit items-center gap-2 text-sm text-muted">
        <input
          type="checkbox"
          checked={autoNext === "1"}
          onChange={(e) => setAutoNext(e.target.checked ? "1" : "0")}
          className="accent-brand"
        />
        {t("player.autoNext")}
      </label>
      {stream && lookedUp && !useOwn && (
        <p className="mt-3 text-sm text-muted">{t("series.embedInfo")}</p>
      )}
    </>
  );
}

const LANGUAGE_NAME_KEYS: Record<string, true> = { German: true, English: true, Japanese: true };

/** The episode's streams, best first. */
function streamsOf(load: Load, key: string, lang: Lang, preference: "dub" | "sub"): SeriesStream[] {
  if (load.key !== key) return [];
  return [...(load.episode?.streams ?? [])]
    .map((stream) => ({ stream, rank: rank(stream, lang, preference) }))
    .sort((a, b) => a.rank - b.rank)
    .map((x) => x.stream);
}
