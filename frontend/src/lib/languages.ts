import type { Language } from "./types";

export const LANGUAGE_ORDER: Language[] = ["de-dub", "de-sub", "en-sub", "en-dub", "unknown"];

export const LANGUAGE_LABELS: Record<Language, string> = {
  "de-dub": "German Dub",
  "de-sub": "German Sub",
  "en-sub": "English Sub",
  "en-dub": "English Dub",
  unknown: "Other",
};
