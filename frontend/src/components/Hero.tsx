import Image from "next/image";
import Link from "next/link";
import { displayTitle, nextEpisode, reasonText, seasonText } from "@/lib/format";
import { formatNumber, genreName } from "@/lib/i18n";
import { getT } from "@/lib/i18n/server";
import type { AnimeDetail } from "@/lib/types";
import { PredictionBadge } from "./PredictionBadge";
import { Synopsis } from "./Synopsis";

export async function Hero({ anime }: { anime: AnimeDetail }) {
  const { t, lang } = await getT();
  const episode = nextEpisode(anime);

  return (
    <section className="relative h-[70vh] min-h-[420px] w-full overflow-hidden">
      {anime.picture_url && (
        // MAL only has portrait posters, so a blurred copy fills the wide banner.
        <Image
          src={anime.picture_url}
          alt=""
          fill
          priority
          sizes="100vw"
          className="scale-110 object-cover opacity-50 blur-2xl"
        />
      )}
      <div className="absolute inset-0 bg-gradient-to-r from-surface via-surface/70 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-surface to-transparent" />

      <div className="relative flex h-full items-end gap-10 px-4 pb-16 md:items-center md:px-12 md:pb-0">
        <div className="max-w-xl">
          {anime.reason && (
            <p className="mb-2 text-sm font-semibold tracking-wide text-brand uppercase">
              {reasonText(t, anime.reason)}
            </p>
          )}
          <h1 className="text-4xl font-black drop-shadow md:text-6xl">{displayTitle(anime)}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-neutral-300">
            <PredictionBadge prediction={anime.prediction} size="md" />
            {anime.mean && <span className="font-semibold text-green-400">★ {formatNumber(lang, anime.mean)}</span>}
            {anime.start_season && <span>{seasonText(t, anime.start_season)}</span>}
            {anime.num_episodes && (
              <span>{t("anime.episodes", { count: anime.num_episodes })}</span>
            )}
            {anime.genres.slice(0, 3).map((g) => (
              <span key={g} className="rounded border border-white/30 px-1.5 text-xs">
                {genreName(lang, g)}
              </span>
            ))}
          </div>
          <Synopsis
            animeId={anime.id}
            text={anime.synopsis}
            language={anime.synopsis_language}
            className="mt-4 line-clamp-3 text-neutral-200 md:text-lg"
          />
          <div className="mt-6 flex gap-3">
            <Link
              href={`/watch/${anime.id}/${episode}`}
              className="flex items-center gap-2 rounded bg-white px-6 py-2 font-semibold text-black hover:bg-white/80"
            >
              ▶ {anime.progress ? t("hero.resume", { episode }) : t("hero.play")}
            </Link>
            <Link
              href={`/anime/${anime.id}`}
              className="rounded bg-neutral-500/60 px-6 py-2 font-semibold hover:bg-neutral-500/40"
            >
              ⓘ {t("hero.moreInfo")}
            </Link>
          </div>
        </div>
        {anime.picture_url && (
          <Image
            src={anime.picture_url}
            alt={displayTitle(anime)}
            width={260}
            height={370}
            className="ml-auto hidden rounded-md shadow-2xl lg:block"
          />
        )}
      </div>
    </section>
  );
}
