import Link from "next/link";
import { notFound } from "next/navigation";
import { PlayerFrame } from "@/components/player/PlayerFrame";
import { apiOrNull } from "@/lib/api";
import { displayTitle } from "@/lib/format";
import type { AnimeDetail } from "@/lib/types";

// Stays mounted across episodes, so the player frame (and its fullscreen) survives "Next Episode".
export default async function WatchLayout({ children, params }: LayoutProps<"/watch/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const anime = await apiOrNull<AnimeDetail>(`/anime/${id}`);
  if (!anime) notFound();

  return (
    <div className="mx-auto max-w-6xl px-4 pt-20 pb-16">
      <PlayerFrame
        back={
          <Link href={`/anime/${anime.id}`} className="text-muted hover:text-white">
            ‹ {displayTitle(anime)}
          </Link>
        }
      >
        {children}
      </PlayerFrame>
    </div>
  );
}
