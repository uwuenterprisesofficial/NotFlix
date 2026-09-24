"use client";

import { LanguageFlag } from "@/components/LanguageFlag";
import { LANGUAGE_LABELS } from "@/lib/languages";
import { Dropdown } from "./Dropdown";
import type { useSources } from "./useSources";

/** The episode's languages, each with its flag. */
export function LanguageMenu({ sources }: { sources: ReturnType<typeof useSources> }) {
  return (
    <Dropdown
      align="left"
      className="w-56"
      button={
        <>
          <LanguageFlag language={sources.language} />
          <span className="truncate font-semibold">{LANGUAGE_LABELS[sources.language]}</span>
        </>
      }
    >
      {(close) =>
        sources.languages.map((lang) => {
          const current = lang === sources.language;
          const count = sources.countIn(lang);
          return (
            <button
              key={lang}
              role="menuitemradio"
              aria-checked={current}
              onClick={() => {
                sources.setLanguage(lang);
                close();
              }}
              className={`flex w-full items-center gap-2 rounded px-2 py-1.5 text-left ${current ? "bg-white/10" : "hover:bg-white/5"}`}
            >
              <span aria-hidden className="w-3 text-xs">
                {current ? "✓" : ""}
              </span>
              <LanguageFlag language={lang} />
              <span className="flex-1 truncate">{LANGUAGE_LABELS[lang]}</span>
              <span className="text-xs text-muted">
                {count} {count === 1 ? "source" : "sources"}
              </span>
            </button>
          );
        })
      }
    </Dropdown>
  );
}
