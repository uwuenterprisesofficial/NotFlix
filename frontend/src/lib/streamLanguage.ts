/**
 * Which stream language is picked: the one chosen for this show (in the episode list or the
 * player), else the first available of dub, then sub in the UI's language, then dub, then sub
 * in the other.
 */
import { useT } from "@/components/I18nProvider";
import { useStoredValue } from "@/components/player/useStoredValue";
import type { Lang } from "./i18n";
import type { Language } from "./types";

export function languageOrder(lang: Lang): Language[] {
  return lang === "de"
    ? ["de-dub", "de-sub", "en-dub", "en-sub", "unknown"]
    : ["en-dub", "en-sub", "de-dub", "de-sub", "unknown"];
}

/** The language to show: the chosen one, else the best available (else the best overall). */
export function pickLanguage(
  order: Language[],
  available: Iterable<Language>,
  chosen: Language | null,
): Language {
  if (chosen) return chosen;
  const have = new Set(available);
  return order.find((l) => have.has(l)) ?? order[0];
}

/** The language picked by hand for this show (null: automatic), and the preference order. */
export function useStreamLanguage(animeId: number) {
  const { lang } = useT();
  const [stored, setStored] = useStoredValue<Language | "">(`notflix:language:${animeId}`, "");
  return {
    order: languageOrder(lang),
    chosen: stored || null,
    choose: (language: Language) => setStored(language),
  };
}
