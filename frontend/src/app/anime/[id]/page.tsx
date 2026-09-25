import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AirTime } from "@/components/AirTime";
import { AnalyzePanel } from "@/components/AnalyzePanel";
import { AnimeToastMapping } from "@/components/AnimeToastMapping";
import { AniWorldMapping } from "@/components/AniWorldMapping";
import { EpisodeBrowser } from "@/components/EpisodeBrowser";
import { LazyDetails } from "@/components/LazyDetails";
import { PredictionPanel } from "@/components/PredictionPanel";
import { WatchTogetherMenu } from "@/components/together/TogetherBar";
import { apiOrNull } from "@/lib/api";
import { Synopsis } from "@/components/Synopsis";
import { displayTitle, formatTime, mediaType, playableEpisode, seasonText } from "@/lib/format";
import { type T, formatNumber, genreName, tagName } from "@/lib/i18n";
import { getT } from "@/lib/i18n/server";
import type { AnimeDetail, Me } from "@/lib/types";
import { allowedImage } from "@/lib/images";

export default async function AnimePage({ params }: PageProps<"/anime/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const { t, lang } = await getT();
  const [anime, me] = await Promise.all([
    apiOrNull<AnimeDetail>(`/anime/${id}?lang=${lang}`),
    apiOrNull<Me>("/me"),
  ]);
  if (!anime) notFound();

  const watched = anime.progress?.episodes_watched ?? 0;
  const title = displayTitle(anime);

  return (
    <div className="px-4 pt-24 pb-16 md:px-12">
      <div className="flex flex-col gap-8 md:flex-row">
        {allowedImage(anime.picture_url) && (
          <Image
            src={allowedImage(anime.picture_url)!}
            alt={title}
            width={240}
            height={340}
            className="h-fit rounded-md shadow-2xl"
          />
        )}
        <div className="max-w-3xl">
          <h1 className="text-3xl font-black md:text-5xl">{title}</h1>
          {anime.title_en && anime.title_en !== anime.title && (
            <p className="mt-1 text-muted">{anime.title}</p>
          )}
          <div className="mt-3 flex flex-wrap gap-3 text-sm text-neutral-300">
            {anime.mean && (
              <span className="font-semibold text-green-400">
                ★ {formatNumber(lang, anime.mean)}
              </span>
            )}
            {anime.media_type && <span>{mediaType(lang, anime.media_type)}</span>}
            {anime.start_season && <span>{seasonText(t, anime.start_season)}</span>}
            {anime.status && <span>{statusText(t, anime.status)}</span>}
            {anime.progress && (
              <span className="text-brand">
                {t(`list.${anime.progress.status}`)} · {watched}/{anime.num_episodes ?? "?"}
              </span>
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {anime.tags.length
              ? anime.tags.map((tag) => (
                  <Link
                    key={tag.id}
                    href={`/search?genre=${tag.id}`}
                    title={t("detail.moreLikeThis", { category: t(`category.${tag.category}`) })}
                    className={`rounded-full px-3 py-1 text-xs hover:bg-white/20 ${tag.category === "genre" ? "bg-surface-raised" : "border border-white/20"}`}
                  >
                    {tagName(lang, tag.id, tag.name)}
                  </Link>
                ))
              : anime.genres.map((g) => (
                  <span key={g} className="rounded-full bg-surface-raised px-3 py-1 text-xs">
                    {genreName(lang, g)}
                  </span>
                ))}
          </div>
          {anime.prediction && <PredictionPanel prediction={anime.prediction} />}
          <Synopsis
            animeId={anime.id}
            text={anime.synopsis}
            language={anime.synopsis_language}
            className="mt-5 whitespace-pre-line text-neutral-200"
            note
          />
          {anime.aired_episodes === 0 ? (
            // Nothing has aired: nothing to play, and no streams are looked for.
            <p className="mt-6 inline-flex flex-wrap items-center gap-2 rounded bg-surface-raised px-4 py-2 text-sm">
              <span className="font-semibold">{t("airing.notAired")}</span>
              {anime.next_episode_at && (
                <span className="text-muted">
                  · {t("airing.firstOn")}
                  <AirTime at={anime.next_episode_at} />
                </span>
              )}
            </p>
          ) : (
            <div className="mt-6 flex flex-wrap items-center gap-4">
              <Link
                href={`/watch/${anime.id}/${anime.resume?.episode ?? playableEpisode(anime)}`}
                className="inline-flex items-center gap-2 rounded bg-white px-6 py-2 font-semibold text-black hover:bg-white/80"
              >
                ▶{" "}
                {anime.resume
                  ? t("detail.resumeAt", {
                      episode: anime.resume.episode,
                      time: formatTime(anime.resume.position_s),
                    })
                  : watched
                    ? t("detail.resume", { episode: playableEpisode(anime) })
                    : t("detail.play1")}
              </Link>
              {me && (
                <WatchTogetherMenu
                  href={`/watch/${anime.id}/${anime.resume?.episode ?? playableEpisode(anime)}`}
                  large
                />
              )}
              {anime.next_episode && anime.next_episode_at && (
                <span className="text-sm text-muted">
                  {t("airing.nextOn", { episode: anime.next_episode })}
                  <AirTime at={anime.next_episode_at} />
                </span>
              )}
            </div>
          )}
        </div>
      </div>

      <EpisodeBrowser
        animeId={anime.id}
        numEpisodes={anime.num_episodes}
        watched={watched}
        signedIn={me !== null && !me.guest}
        aired={anime.aired_episodes}
        nextAt={anime.next_episode_at}
      />

      {me && !me.guest && (
        // Rarely needed: fixing a wrong source match, and intro/outro detection.
        // Its panels load their data only once it's opened.
        <LazyDetails
          className="group mt-12 max-w-2xl"
          summary={
            <summary className="flex w-fit cursor-pointer list-none items-center gap-2 rounded bg-surface-raised px-4 py-2 text-sm font-semibold hover:bg-neutral-700 [&::-webkit-details-marker]:hidden">
              <span aria-hidden className="transition-transform group-open:rotate-90">
                ▸
              </span>
              {t("detail.moreOptions")}
              <span className="font-normal text-muted">{t("detail.moreOptionsInfo")}</span>
            </summary>
          }
        >
          <AniWorldMapping animeId={anime.id} />
          <AnimeToastMapping animeId={anime.id} />
          <AnalyzePanel animeId={anime.id} signedIn />
        </LazyDetails>
      )}
    </div>
  );
}

function statusText(t: T, status: string): string {
  return ["finished_airing", "currently_airing", "not_yet_aired"].includes(status)
    ? t(`status.${status}` as "status.finished_airing")
    : status.replaceAll("_", " ");
}
