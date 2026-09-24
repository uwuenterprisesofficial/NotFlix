import Image from "next/image";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AnalyzePanel } from "@/components/AnalyzePanel";
import { AnimeToastMapping } from "@/components/AnimeToastMapping";
import { AniWorldMapping } from "@/components/AniWorldMapping";
import { EpisodeBrowser } from "@/components/EpisodeBrowser";
import { apiOrNull } from "@/lib/api";
import { displayTitle, nextEpisode } from "@/lib/format";
import type { AnimeDetail, Me } from "@/lib/types";

// Airing shows have no episode count on MAL yet; analyse within a reasonable default range.
const UNKNOWN_EPISODE_COUNT = 12;

export default async function AnimePage({ params }: PageProps<"/anime/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const [anime, me] = await Promise.all([
    apiOrNull<AnimeDetail>(`/anime/${id}`),
    apiOrNull<Me>("/me"),
  ]);
  if (!anime) notFound();

  const watched = anime.progress?.episodes_watched ?? 0;
  const count = anime.num_episodes ?? Math.max(watched + 1, UNKNOWN_EPISODE_COUNT);
  const title = displayTitle(anime);

  return (
    <div className="px-4 pt-24 pb-16 md:px-12">
      <div className="flex flex-col gap-8 md:flex-row">
        {anime.picture_url && (
          <Image
            src={anime.picture_url}
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
            {anime.mean && <span className="font-semibold text-green-400">★ {anime.mean}</span>}
            {anime.media_type && <span className="uppercase">{anime.media_type}</span>}
            {anime.start_season && <span className="capitalize">{anime.start_season}</span>}
            {anime.status && (
              <span className="capitalize">{anime.status.replaceAll("_", " ")}</span>
            )}
            {anime.progress && (
              <span className="text-brand capitalize">
                {anime.progress.status.replaceAll("_", " ")} · {watched}/{anime.num_episodes ?? "?"}
              </span>
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {anime.genres.map((g) => (
              <span key={g} className="rounded-full bg-surface-raised px-3 py-1 text-xs">
                {g}
              </span>
            ))}
          </div>
          {anime.synopsis && (
            <p className="mt-5 whitespace-pre-line text-neutral-200">{anime.synopsis}</p>
          )}
          <Link
            href={`/watch/${anime.id}/${nextEpisode(anime)}`}
            className="mt-6 inline-flex items-center gap-2 rounded bg-white px-6 py-2 font-semibold text-black hover:bg-white/80"
          >
            ▶ {watched ? `Resume episode ${nextEpisode(anime)}` : "Play episode 1"}
          </Link>
        </div>
      </div>

      <EpisodeBrowser
        animeId={anime.id}
        numEpisodes={anime.num_episodes}
        watched={watched}
        signedIn={me !== null}
      />

      {me && (
        // Rarely needed: fixing a wrong source match, and intro/outro detection.
        <details className="group mt-12 max-w-2xl">
          <summary className="flex w-fit cursor-pointer list-none items-center gap-2 rounded bg-surface-raised px-4 py-2 text-sm font-semibold hover:bg-neutral-700 [&::-webkit-details-marker]:hidden">
            <span aria-hidden className="transition-transform group-open:rotate-90">
              ▸
            </span>
            More options
            <span className="font-normal text-muted">
              AniWorld &amp; AnimeToast pages, intro &amp; outro detection
            </span>
          </summary>
          <AniWorldMapping animeId={anime.id} />
          <AnimeToastMapping animeId={anime.id} />
          <AnalyzePanel animeId={anime.id} episodeCount={count} signedIn />
        </details>
      )}
    </div>
  );
}
