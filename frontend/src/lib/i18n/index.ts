import { type Lang, LOCALE, type Messages, interpolate } from "./core";
import { admin } from "./messages/admin";
import { analysis } from "./messages/analysis";
import { common } from "./messages/common";
import { detail } from "./messages/detail";
import { player } from "./messages/player";
import { search } from "./messages/search";
import { stats } from "./messages/stats";
import { mediaTypes, sources, tags } from "./messages/tags";
import { together } from "./messages/together";

export * from "./core";

const messages = {
  ...common,
  ...detail,
  ...player,
  ...analysis,
  ...search,
  ...stats,
  ...together,
  ...admin,
} satisfies Messages;

export type MessageKey = keyof typeof messages;
type Params<K extends MessageKey> = (typeof messages)[K]["en"] extends (
  v: infer V,
  ...rest: never[]
) => string
  ? V
  : Record<string, string | number> | undefined;

export type T = <K extends MessageKey>(key: K, vars?: Params<K>) => string;

export function translator(lang: Lang): T {
  return (key, vars) => {
    const message = messages[key][lang];
    return typeof message === "function"
      ? (message as (v: unknown, lang: Lang) => string)(vars, lang)
      : interpolate(message, vars as Record<string, string | number> | undefined);
  };
}

/** Numbers in the UI's locale. */
export function formatNumber(lang: Lang, value: number, digits?: number): string {
  return value.toLocaleString(LOCALE[lang], {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits ?? 3,
  });
}

/** MAL's genre/theme/demographic names are English; German ones where they differ. */
export function tagName(lang: Lang, id: number, name: string): string {
  return tags[id]?.[lang] ?? name;
}

const TAG_BY_NAME = new Map(Object.values(tags).map((names) => [names.en.toLowerCase(), names]));

/** The same, when only MAL's (English) name is known. */
export function genreName(lang: Lang, name: string): string {
  return TAG_BY_NAME.get(name.toLowerCase())?.[lang] ?? name;
}

/** The name of a prediction feature or statistics row (tag:<id>, studio:…, source:…, type:…,
 * era:<decade>, mal, popularity) in the UI's language. */
export function featureName(lang: Lang, key: string, name: string): string {
  const t = translator(lang);
  const cut = key.indexOf(":");
  const prefix = cut < 0 ? key : key.slice(0, cut);
  const value = cut < 0 ? "" : key.slice(cut + 1);
  if (key === "mal") return t("feature.mal");
  if (key === "popularity") return t("feature.popularity");
  if (prefix === "tag") return tagName(lang, Number(value), name);
  if (prefix === "era") return t("feature.era", { decade: value });
  if (prefix === "source") return sources[value]?.[lang] ?? name;
  if (prefix === "type") return mediaTypes[value]?.[lang] ?? name;
  return name;
}

export function mediaTypeName(lang: Lang, type: string): string {
  return mediaTypes[type]?.[lang] ?? type.toUpperCase();
}
