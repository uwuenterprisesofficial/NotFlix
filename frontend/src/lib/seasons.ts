import type { SeasonName } from "./types";

export const SEASONS: SeasonName[] = ["winter", "spring", "summer", "fall"];

export function currentSeason(now = new Date()): { year: number; season: SeasonName } {
  return { year: now.getUTCFullYear(), season: SEASONS[Math.floor(now.getUTCMonth() / 3)] };
}

/** The season `by` seasons before (negative) or after this one. */
export function stepSeason(year: number, season: SeasonName, by: number) {
  const index = year * 4 + SEASONS.indexOf(season) + by;
  return { year: Math.floor(index / 4), season: SEASONS[((index % 4) + 4) % 4] };
}

export function seasonHref({ year, season }: { year: number; season: SeasonName }) {
  return `/seasons/${year}/${season}`;
}
