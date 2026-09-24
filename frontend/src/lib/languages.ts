import type { Language } from "./types";

export const LANGUAGE_ORDER: Language[] = ["de-dub", "de-sub", "en-sub", "en-dub", "unknown"];

export const LANGUAGE_LABELS: Record<Language, string> = {
  "de-dub": "German Dub",
  "de-sub": "German Sub",
  "en-sub": "English Sub",
  "en-dub": "English Dub",
  unknown: "Other",
};

export const LANGUAGE_SHORT: Record<Language, string> = {
  "de-dub": "DE",
  "de-sub": "DE Sub",
  "en-sub": "EN Sub",
  "en-dub": "EN",
  unknown: "?",
};

export const PROVIDER_LABELS: Record<string, string> = {
  aniworld: "AniWorld",
  anivexa: "Anivexa",
  reanime: "ReAnime",
  database: "Your sources",
};
