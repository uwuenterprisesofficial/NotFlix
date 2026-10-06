/**
 * Which stream language is picked: the one chosen for this show (in the episode list or the
 * player), else the first available in the order the settings ask for: preferring dubs, the
 * dub in the UI's language, then its subtitles, then the other language's; preferring subs,
 * subtitles first (German subtitles, then English ones for a German UI; for an English one,
 * the English dub comes before German subtitles).
 */
import { useT } from "@/components/I18nProvider";
import { useStoredValue } from "@/components/player/useStoredValue";
import { type AudioPreference, useAudioPreference } from "./preferences";
import type { Lang } from "./i18n";
import type { Language } from "./types";

export function languageOrder(lang: Lang, audio: AudioPreference = "dub"): Language[] {
  if (audio === "sub") {
    return lang === "de"
      ? ["de-sub", "en-sub", "de-dub", "en-dub", "unknown"]
      : ["en-sub", "en-dub", "de-sub", "de-dub", "unknown"];
  }
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
  const [audio] = useAudioPreference();
  const [stored, setStored] = useStoredValue<Language | "">(`notflix:language:${animeId}`, "");
  return {
    order: languageOrder(lang, audio),
    chosen: stored || null,
    choose: (language: Language) => setStored(language),
  };
}
