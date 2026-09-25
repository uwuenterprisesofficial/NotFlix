import { LOCALE, type Lang, type T, mediaTypeName } from "./i18n";

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

const LIKED = "Because you liked ";

/** A recommendation's reason (the backend stores it in English) in the UI's language. */
export function reasonText(t: T, reason: string): string {
  return reason.startsWith(LIKED)
    ? t("reason.becauseYouLiked", { title: reason.slice(LIKED.length) })
    : reason;
}

/** MAL's "spring 2009" in the UI's language. */
export function seasonText(t: T, startSeason: string): string {
  const [season, year] = startSeason.split(" ");
  const key = `season.${season}` as const;
  return ["winter", "spring", "summer", "fall"].includes(season)
    ? t(key as "season.spring", { year })
    : startSeason;
}

export function mediaType(lang: Lang, type: string): string {
  return mediaTypeName(lang, type);
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
];

/** "5 hours ago", "in 2 days" in the UI's language. */
export function relativeTime(lang: Lang, when: string | Date, now = Date.now()): string {
  const diff = new Date(when).getTime() - now;
  const format = new Intl.RelativeTimeFormat(LOCALE[lang], { numeric: "auto", style: "short" });
  for (const [unit, ms] of UNITS) {
    if (Math.abs(diff) >= ms || unit === "minute")
      return format.format(Math.round(diff / ms), unit);
  }
  return format.format(0, "minute");
}

/** "Sat 27 Sep, 18:30" in the viewer's time zone. */
export function airTime(lang: Lang, when: string | Date): string {
  return new Date(when).toLocaleString(LOCALE[lang], {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** The episode to open when pressing Play, within the aired ones. */
export function playableEpisode(anime: {
  num_episodes: number | null;
  progress: { episodes_watched: number } | null;
  aired_episodes?: number | null;
}): number {
  const next = nextEpisode(anime);
  return anime.aired_episodes ? Math.min(next, anime.aired_episodes) : next;
}
