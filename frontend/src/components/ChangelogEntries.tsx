"use client";

import { type ChangelogEntry, shortVersion } from "@/lib/changelog";
import { useT } from "./I18nProvider";

/** Changelog entries: the version, its date and title, and what's new. */
export function ChangelogEntries({ entries }: { entries: ChangelogEntry[] }) {
  const { t, lang } = useT();
  return (
    <div className="space-y-8">
      {entries.map((entry) => (
        <article key={entry.version}>
          <h2 className="flex flex-wrap items-baseline gap-x-3 text-xl font-bold">
            {t("changelog.version", { version: shortVersion(entry.version) })}
            <span className="text-base font-semibold text-white/80">{entry.title[lang]}</span>
            <time dateTime={entry.date} className="text-sm font-normal text-muted">
              {new Date(`${entry.date}T12:00:00Z`).toLocaleDateString(lang, {
                dateStyle: "long",
              })}
            </time>
          </h2>
          <ul className="mt-3 space-y-3">
            {entry.items.map((item) => (
              <li key={item.title.en} className="flex gap-3">
                <span aria-hidden className="mt-0.5 text-brand">
                  ✦
                </span>
                <span>
                  <span className="font-semibold">{item.title[lang]}</span>
                  <span className="block text-sm text-muted">{item.text[lang]}</span>
                </span>
              </li>
            ))}
          </ul>
        </article>
      ))}
    </div>
  );
}
