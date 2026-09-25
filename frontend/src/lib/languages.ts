import type { T } from "./i18n";

export const PROVIDER_LABELS: Record<string, string> = {
  aniworld: "AniWorld",
  animetoast: "AnimeToast",
  anivexa: "Anivexa",
  reanime: "ReAnime",
};

export function providerLabel(t: T, provider: string): string {
  return provider === "database"
    ? t("player.yourSources")
    : (PROVIDER_LABELS[provider] ?? provider);
}
