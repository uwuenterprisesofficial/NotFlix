/**
 * UI translations. Every message has an English and a German version side by side (see
 * messages/), so neither language can miss one. A message is a string with {placeholders}, or
 * a function for anything that needs more (plurals, formatting).
 */
export const LANGS = ["en", "de"] as const;
export type Lang = (typeof LANGS)[number];
export const DEFAULT_LANG: Lang = "en";
export const LANG_COOKIE = "notflix_lang";

export type Vars = Record<string, string | number>;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type Message = string | ((v: any, lang: Lang) => string);
export type Messages = Record<string, { en: Message; de: Message }>;

export const LOCALE: Record<Lang, string> = { en: "en-US", de: "de-DE" };

export function isLang(value: unknown): value is Lang {
  return LANGS.includes(value as Lang);
}

/** The best language for an Accept-Language header. */
export function fromAcceptLanguage(header: string | null | undefined): Lang {
  for (const part of (header ?? "").split(",")) {
    const code = part.trim().slice(0, 2).toLowerCase();
    if (isLang(code)) return code;
  }
  return DEFAULT_LANG;
}

export function interpolate(text: string, vars?: Vars): string {
  return vars ? text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : text;
}

/** Remember the chosen language (a cookie, so server-rendered pages use it too). */
export function saveLang(lang: Lang): void {
  document.cookie = `${LANG_COOKIE}=${lang}; path=/; max-age=${60 * 60 * 24 * 365 * 2}; samesite=lax`;
}
