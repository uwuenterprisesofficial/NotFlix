"use client";

import { useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { formatNumber, type MessageKey, tagName } from "@/lib/i18n";
import { type Order, readQuery, searchHref } from "@/lib/search";
import type { Genre, TagCategory } from "@/lib/types";
import { useT } from "./I18nProvider";

const GROUPS: { category: TagCategory; label: MessageKey }[] = [
  { category: "genre", label: "search.groupGenre" },
  { category: "theme", label: "search.groupTheme" },
  { category: "demographic", label: "search.groupDemographic" },
  { category: "explicit", label: "search.groupExplicit" },
];

const ORDER_LABEL = {
  score: "search.orderScore",
  popularity: "search.orderPopularity",
  newest: "search.orderNewest",
  for_you: "search.orderForYou",
} as const;

// Typing searches by itself after this pause.
const TYPING_PAUSE_MS = 350;

/** Title, genre and order of the search page. They live in its URL, changed without a page
 * load (the results below fetch what they show): typing replaces the current history entry,
 * a submitted search or another genre/order adds one. */
export function SearchControls({ genres }: { genres: Genre[] }) {
  const { t, lang } = useT();
  const params = useSearchParams();
  const { q, genre: genreId, order } = readQuery(params);
  const [text, setText] = useState(q);
  // The URL changed by itself (back/forward): show its query.
  const [shown, setShown] = useState(q);
  if (q !== shown) {
    setShown(q);
    setText(q);
  }
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  function go(next: { q?: string; genre?: number | null; order?: Order }, replace = false) {
    clearTimeout(timer.current);
    const href = searchHref({
      q: (next.q ?? text).trim(),
      genre: next.genre === undefined ? genreId : next.genre,
      order: next.order ?? order,
    });
    if (href === `/search${params.size ? `?${params}` : ""}`) return;
    if (replace) window.history.replaceState(null, "", href);
    else window.history.pushState(null, "", href);
  }

  function type(value: string) {
    setText(value);
    clearTimeout(timer.current);
    // Searching starts once typing pauses (not for every letter).
    timer.current = setTimeout(() => go({ q: value }, true), TYPING_PAUSE_MS);
  }

  return (
    <form
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        go({});
      }}
      className="mt-4 flex flex-wrap items-center gap-3"
    >
      <input
        type="search"
        name="q"
        value={text}
        onChange={(e) => type(e.target.value)}
        autoFocus={!q}
        placeholder={t("search.placeholder")}
        aria-label={t("search.titleLabel")}
        className="min-w-0 flex-1 basis-64 rounded border border-white/20 bg-surface-raised px-3 py-2 outline-none focus:border-white/60"
      />
      <select
        aria-label={t("search.genre")}
        value={genreId ?? ""}
        onChange={(e) => go({ genre: e.target.value ? Number(e.target.value) : null })}
        className="rounded border border-white/20 bg-surface-raised px-3 py-2"
      >
        <option value="">{t("search.anyGenre")}</option>
        {GROUPS.map(({ category, label }) => {
          const items = genres
            .filter((g) => g.category === category)
            .map((g) => ({ ...g, label: tagName(lang, g.id, g.name) }))
            .sort((a, b) => a.label.localeCompare(b.label, lang));
          return items.length ? (
            <optgroup key={category} label={t(label)}>
              {items.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.label}
                  {g.count ? ` (${formatNumber(lang, g.count)})` : ""}
                </option>
              ))}
            </optgroup>
          ) : null;
        })}
      </select>
      <select
        aria-label={t("search.order")}
        value={order}
        onChange={(e) => go({ order: e.target.value as Order })}
        className="rounded border border-white/20 bg-surface-raised px-3 py-2"
        title={q ? t("search.orderInfo") : undefined}
      >
        {Object.entries(ORDER_LABEL).map(([value, label]) => (
          <option
            key={value}
            value={value}
            disabled={!!q && value !== "score" && value !== "for_you"}
          >
            {q && value === "score" ? t("search.bestMatch") : t(label)}
          </option>
        ))}
      </select>
      <button className="rounded bg-brand px-5 py-2 font-semibold hover:bg-brand-dark">
        {t("search.submit")}
      </button>
    </form>
  );
}
