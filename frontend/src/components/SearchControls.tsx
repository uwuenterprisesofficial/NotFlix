"use client";

import { useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { formatNumber, type MessageKey, tagName } from "@/lib/i18n";
import { type Order, readQuery, type SearchQuery, searchHref } from "@/lib/search";
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
  const query = readQuery(params);
  const { q, genre: genreId, order, dub } = query;
  const [text, setText] = useState(q);
  // The URL changed by itself (back/forward): show its query.
  const [shown, setShown] = useState(q);
  if (q !== shown) {
    setShown(q);
    setText(q);
  }
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  function go(next: Partial<SearchQuery>, replace = false) {
    clearTimeout(timer.current);
    // A changed search starts on its first page.
    const href = searchHref({ ...query, ...next, q: (next.q ?? text).trim(), page: 1 });
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
      <label
        className="flex items-center gap-2 rounded border border-white/20 bg-surface-raised px-3 py-2 text-sm"
        title={t("search.dubInfo")}
      >
        <input
          type="checkbox"
          checked={dub}
          onChange={(e) => go({ dub: e.target.checked })}
          className="accent-brand"
        />
        {t("search.dub")}
      </label>
      <button className="rounded bg-brand px-5 py-2 font-semibold hover:bg-brand-dark">
        {t("search.submit")}
      </button>
      <SearchFilters query={query} onChange={(f) => go(f)} />
    </form>
  );
}

const SCORES = [5, 6, 7, 7.5, 8, 8.5, 9];

/** Hide what's been seen; MAL's score and the predicted score between two values. */
function SearchFilters({
  query,
  onChange,
}: {
  query: SearchQuery;
  onChange: (next: Partial<SearchQuery>) => void;
}) {
  const { t, lang } = useT();
  const range = (
    label: string,
    min: number | null,
    max: number | null,
    keys: ["minScore" | "minPredicted", "maxScore" | "maxPredicted"],
  ) => {
    const select = (value: number | null, key: keyof SearchQuery, any: string) => (
      <select
        aria-label={`${label}: ${any}`}
        value={value ?? ""}
        onChange={(e) => onChange({ [key]: e.target.value === "" ? null : Number(e.target.value) })}
        className="rounded border border-white/20 bg-surface-raised px-2 py-1"
      >
        <option value="">{any}</option>
        {SCORES.map((s) => (
          <option key={s} value={s}>
            {formatNumber(lang, s)}
          </option>
        ))}
      </select>
    );
    return (
      <span className="flex items-center gap-1.5">
        {label}
        {select(min, keys[0], t("search.min"))}–{select(max, keys[1], t("search.max"))}
      </span>
    );
  };
  return (
    <div className="flex w-full flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted">
      <label className="flex items-center gap-2" title={t("search.hideSeenInfo")}>
        <input
          type="checkbox"
          checked={query.hideSeen}
          onChange={(e) => onChange({ hideSeen: e.target.checked })}
          className="accent-brand"
        />
        {t("search.hideSeen")}
      </label>
      {range(t("search.malScore"), query.minScore, query.maxScore, ["minScore", "maxScore"])}
      {range(t("search.predictedScore"), query.minPredicted, query.maxPredicted, [
        "minPredicted",
        "maxPredicted",
      ])}
    </div>
  );
}
