import Link from "next/link";
import { notFound } from "next/navigation";
import { Player } from "@/components/player/Player";
import { api, apiOrNull } from "@/lib/api";
import { displayTitle } from "@/lib/format";
import type { AnimeDetail, Episode, Me } from "@/lib/types";

export default async function WatchPage({ params }: PageProps<"/watch/[id]/[episode]">) {
  const { id, episode: episodeParam } = await params;
  const episode = Number(episodeParam);
  if (!/^\d+$/.test(id) || !Number.isInteger(episode) || episode < 1) notFound();

  const [anime, data, me] = await Promise.all([
    apiOrNull<AnimeDetail>(`/anime/${id}`),
    api<Episode>(`/anime/${id}/episodes/${episode}`),
    apiOrNull<Me>("/me"),
  ]);
  if (!anime || (anime.num_episodes && episode > anime.num_episodes)) notFound();

  return (
    <div className="mx-auto max-w-6xl px-4 pt-20 pb-16">
      <div className="mb-4 flex items-baseline gap-3">
        <Link href={`/anime/${anime.id}`} className="text-muted hover:text-white">
          ‹ {displayTitle(anime)}
        </Link>
        <h1 className="text-xl font-semibold">Episode {episode}</h1>
      </div>
      <Player
        key={episode}
        animeId={anime.id}
        episode={episode}
        sources={data.sources}
        segments={data.skip_segments}
        hasNext={!anime.num_episodes || episode < anime.num_episodes}
        signedIn={me !== null}
        watched={anime.progress?.episodes_watched ?? 0}
      />
    </div>
  );
}
