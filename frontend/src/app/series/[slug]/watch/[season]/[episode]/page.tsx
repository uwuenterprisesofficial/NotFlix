import { SeriesPlayer } from "@/components/series/SeriesPlayer";
import { notFound } from "next/navigation";

export default async function SeriesWatchPage({
  params,
}: PageProps<"/series/[slug]/watch/[season]/[episode]">) {
  const { slug, season, episode } = await params;
  if (!/^\d+$/.test(season) || !/^\d+$/.test(episode) || Number(episode) < 1) notFound();
  return (
    <SeriesPlayer slug={decodeURIComponent(slug)} season={Number(season)} episode={Number(episode)} />
  );
}
