"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { formatNumber, type MessageKey, tagName } from "@/lib/i18n";
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

export function SearchControls({
  q,
  genreId,
  order,
  genres,
}: {
  q: string;
  genreId: number | null;
  order: keyof typeof ORDER_LABEL;
  genres: Genre[];
}) {
  const { t, lang } = useT();
  const router = useRouter();
  const [text, setText] = useState(q);

  function go(next: { q?: string; genre?: number | null; order?: string }) {
    const query = new URLSearchParams();
    const nq = (next.q ?? text).trim();
    const genre = next.genre === undefined ? genreId : next.genre;
    const nextOrder = next.order ?? order;
    if (nq) query.set("q", nq);
    if (genre) query.set("genre", String(genre));
    if (nextOrder !== "score") query.set("order", nextOrder);
    router.push(`/search?${query}`);
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
        onChange={(e) => setText(e.target.value)}
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
        onChange={(e) => go({ order: e.target.value })}
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
