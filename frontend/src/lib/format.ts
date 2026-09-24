export function formatTime(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const rest = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${rest}` : `${m}:${rest}`;
}

export function displayTitle(anime: { title: string; title_en: string | null }): string {
  return anime.title_en || anime.title;
}

/** The episode to open when pressing Play: the next unwatched one, clamped to the last episode. */
export function nextEpisode(anime: {
  num_episodes: number | null;
  progress: { episodes_watched: number } | null;
}): number {
  const next = (anime.progress?.episodes_watched ?? 0) + 1;
  return anime.num_episodes ? Math.min(next, anime.num_episodes) : next;
}
