import { nextEpisode } from "./format";
import type { AnimeCard } from "./types";

export type PrefetchShow = { id: number; episode: number };

/** The shows of a page whose streams are worth looking for in the background (in the page's
 * order, around the user's next episode): not the ones that haven't aired. */
export function prefetchShows(cards: (AnimeCard | null | undefined)[]): PrefetchShow[] {
  const seen = new Set<number>();
  const shows: PrefetchShow[] = [];
  for (const card of cards) {
    if (!card || seen.has(card.id) || card.status === "not_yet_aired") continue;
    seen.add(card.id);
    // An airing show's next episode may not be out yet: the latest one that is.
    const aired = card.next_episode ? card.next_episode - 1 : null;
    const episode = Math.max(1, aired ? Math.min(nextEpisode(card), aired) : nextEpisode(card));
    shows.push({ id: card.id, episode });
  }
  return shows;
}
