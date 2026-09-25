"use client";

import { createContext, useContext, useMemo } from "react";
import { type Lang, translator } from "@/lib/i18n";

const LangContext = createContext<Lang>("en");

/** Makes the UI language (from the server: cookie or browser) available to client components. */
export function I18nProvider({ lang, children }: { lang: Lang; children: React.ReactNode }) {
  return <LangContext.Provider value={lang}>{children}</LangContext.Provider>;
}

export function useT() {
  const lang = useContext(LangContext);
  const t = useMemo(() => translator(lang), [lang]);
  return { lang, t };
}
