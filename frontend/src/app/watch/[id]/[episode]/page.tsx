import Link from "next/link";
import { notFound } from "next/navigation";
import { AirTime } from "@/components/AirTime";
import { Player } from "@/components/player/Player";
import { api, apiOrNull } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import type { AnimeDetail, Episode, Me } from "@/lib/types";

export default async function WatchPage({
  params,
  searchParams,
}: PageProps<"/watch/[id]/[episode]">) {
  const { id, episode: episodeParam } = await params;
  const query = await searchParams;
  const param = (name: string) => (typeof query[name] === "string" ? query[name] : null);
  const episode = Number(episodeParam);
  if (!/^\d+$/.test(id) || !Number.isInteger(episode) || episode < 1) notFound();

  const [anime, data, me] = await Promise.all([
    apiOrNull<AnimeDetail>(`/anime/${id}`),
    api<Episode>(`/anime/${id}/episodes/${episode}`),
    apiOrNull<Me>("/me"),
  ]);
  if (!anime || (anime.num_episodes && episode > anime.num_episodes)) notFound();

  const aired = anime.aired_episodes;
  if (aired !== null && episode > aired) {
    // Not aired: no streams exist yet, so none are looked for.
    const { t } = await getT();
    const airsAt = episode === anime.next_episode ? anime.next_episode_at : null;
    return (
      <div className="grid aspect-video place-items-center rounded bg-surface-raised p-6 text-center">
        <div>
          <p className="text-lg font-semibold">{t("airing.notYetTitle", { episode })}</p>
          {airsAt && (
            <p className="mt-2 text-muted">
              {t("airing.nextOn", { episode })}
              <AirTime at={airsAt} />
            </p>
          )}
          <p className="mt-2 text-sm text-muted">{t("airing.notYetInfo")}</p>
          <Link href={`/anime/${anime.id}`} className="mt-4 inline-block text-sm underline">
            {t("airing.back")}
          </Link>
        </div>
      </div>
    );
  }

  // The heading and the player frame come from the layout.
  return (
    <Player
      key={episode}
      animeId={anime.id}
      episode={episode}
      segments={data.skip_segments}
      hasNext={episode < (aired ?? anime.num_episodes ?? Infinity)}
      signedIn={me !== null}
      watched={anime.progress?.episodes_watched ?? 0}
      via={{ provider: param("via"), label: param("option") }}
      server={param("server")}
    />
  );
}
