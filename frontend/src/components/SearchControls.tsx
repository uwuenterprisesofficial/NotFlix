"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { Genre, TagCategory } from "@/lib/types";

const GROUPS: { category: TagCategory; label: string }[] = [
  { category: "genre", label: "Genres" },
  { category: "theme", label: "Themes" },
  { category: "demographic", label: "Demographics" },
  { category: "explicit", label: "Explicit genres" },
];

const ORDER_LABEL = {
  score: "Top rated",
  popularity: "Most popular",
  newest: "Newest",
  for_you: "Best for you",
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
        placeholder="Search anime on MyAnimeList…"
        aria-label="Title"
        className="min-w-0 flex-1 basis-64 rounded border border-white/20 bg-surface-raised px-3 py-2 outline-none focus:border-white/60"
      />
      <select
        aria-label="Genre"
        value={genreId ?? ""}
        onChange={(e) => go({ genre: e.target.value ? Number(e.target.value) : null })}
        className="rounded border border-white/20 bg-surface-raised px-3 py-2"
      >
        <option value="">Any genre</option>
        {GROUPS.map(({ category, label }) => {
          const items = genres.filter((g) => g.category === category);
          return items.length ? (
            <optgroup key={category} label={label}>
              {items.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                  {g.count ? ` (${g.count.toLocaleString("en")})` : ""}
                </option>
              ))}
            </optgroup>
          ) : null;
        })}
      </select>
      <select
        aria-label="Order"
        value={order}
        onChange={(e) => go({ order: e.target.value })}
        className="rounded border border-white/20 bg-surface-raised px-3 py-2"
        title={q ? "MAL's title search has its own order; this sorts the page" : undefined}
      >
        {Object.entries(ORDER_LABEL).map(([value, label]) => (
          <option
            key={value}
            value={value}
            disabled={!!q && value !== "score" && value !== "for_you"}
          >
            {q && value === "score" ? "Best match" : label}
          </option>
        ))}
      </select>
      <button className="rounded bg-brand px-5 py-2 font-semibold hover:bg-brand-dark">
        Search
      </button>
    </form>
  );
}
