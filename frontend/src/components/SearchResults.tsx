"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { tagName } from "@/lib/i18n";
import { readQuery, type SearchQuery, searchHref } from "@/lib/search";
import type { Genre, SearchResponse } from "@/lib/types";
import { AnimeCard } from "./AnimeCard";
import { useT } from "./I18nProvider";

const GRID =
  "mt-4 grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-x-3 gap-y-6 md:grid-cols-[repeat(auto-fill,minmax(11rem,1fr))]";

// Answers seen in this tab, so going back and forth between searches is instant.
const answers = new Map<string, SearchResponse>();

async function load(url: string, signal: AbortSignal): Promise<SearchResponse> {
  const cached = answers.get(url);
  if (cached) return cached;
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(String(res.status));
  const body = (await res.json()) as SearchResponse;
  answers.set(url, body);
  return body;
}

/** The search's results, fetched here rather than before the page shows: shows NotFlix already
 * knows come first (milliseconds), MyAnimeList's results replace them once they arrive. */
export function SearchResults({ genres }: { genres: Genre[] }) {
  const query = readQuery(useSearchParams());
  // A new search starts afresh (no results of the previous one in between).
  return <Results key={searchHref(query)} query={query} genres={genres} />;
}

type State = {
  /** The catalogue's matches (a title search only): shown until `full` is there. */
  quick: SearchResponse | null;
  full: SearchResponse | null;
  failed: boolean;
};

function Results({ query, genres }: { query: SearchQuery; genres: Genre[] }) {
  const { t, lang } = useT();
  const { q, genre: genreId, order, page } = query;
  const genre = genres.find((g) => g.id === genreId) ?? null;
  const [state, setState] = useState<State>({ quick: null, full: null, failed: false });

  useEffect(() => {
    if (!q && !genreId) return;
    const abort = new AbortController();
    if (q) {
      const params = (quick: boolean) =>
        new URLSearchParams({ q, page: String(page), ...(quick ? { quick: "true" } : {}) });
      load(`/api/search?${params(true)}`, abort.signal)
        .then((quick) => setState((s) => ({ ...s, quick })))
        .catch(() => {});
      load(`/api/search?${params(false)}`, abort.signal)
        .then((full) => setState((s) => ({ ...s, full })))
        .catch(() => !abort.signal.aborted && setState((s) => ({ ...s, failed: true })));
    } else {
      const apiOrder = order === "for_you" ? "score" : order;
      load(
        `/api/search/genre/${genreId}?${new URLSearchParams({ order: apiOrder, page: String(page) })}`,
        abort.signal,
      )
        .then((full) => setState((s) => ({ ...s, full })))
        .catch(() => !abort.signal.aborted && setState((s) => ({ ...s, failed: true })));
    }
    return () => abort.abort();
  }, [q, genreId, order, page]);

  if (!q && !genreId) return <p className="mt-10 text-muted">{t("search.intro")}</p>;

  const shown = state.full ?? state.quick;
  const busy = !state.full && !state.failed;
  let items = shown?.items ?? [];
  // MAL's search can't filter by genre: this page is narrowed down to it here.
  if (q && genre) items = items.filter((a) => a.genres.includes(genre.name));
  if (order === "for_you") {
    items = [...items].sort((a, b) => (b.prediction?.score ?? 0) - (a.prediction?.score ?? 0));
  }
  const genreLabel = genre ? tagName(lang, genre.id, genre.name) : null;
  const heading = q
    ? t("search.resultsFor", { q }) + (genreLabel ? t("search.inGenre", { genre: genreLabel }) : "")
    : (genreLabel ?? "");

  const goTo = (p: number) => {
    window.history.pushState(null, "", searchHref({ ...query, page: p }));
    window.scrollTo({ top: 0 });
  };

  return (
    <>
      <div className="mt-6 flex min-h-5 items-center gap-3 text-sm text-muted">
        <span>
          {heading}
          {state.full?.source === "local" && t("search.local")}
        </span>
        {busy && <Searching label={shown ? t("search.searchingMore") : t("search.searching")} />}
        {state.failed && !state.full && <span className="text-red-400">{t("search.failed")}</span>}
      </div>
      {busy && <ProgressBar />}
      {!shown && busy ? (
        <Skeleton />
      ) : items.length === 0 ? (
        !busy && <p className="mt-10 text-muted">{t("search.nothing")}</p>
      ) : (
        <div className={`${GRID} transition-opacity ${busy ? "opacity-80" : ""}`}>
          {items.map((anime) => (
            <div key={anime.id}>
              <AnimeCard anime={anime} fluid />
            </div>
          ))}
        </div>
      )}
      {state.full && (page > 1 || state.full.has_next) && (
        <nav className="mt-10 flex items-center justify-center gap-4 text-sm">
          {page > 1 && (
            <button
              onClick={() => goTo(page - 1)}
              className="rounded bg-surface-raised px-4 py-2 hover:bg-white/10"
            >
              {t("search.previous")}
            </button>
          )}
          <span className="text-muted">{t("search.page", { page })}</span>
          {state.full.has_next && (
            <button
              onClick={() => goTo(page + 1)}
              className="rounded bg-surface-raised px-4 py-2 hover:bg-white/10"
            >
              {t("search.next")}
            </button>
          )}
        </nav>
      )}
    </>
  );
}

function Searching({ label }: { label: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2">
      <span
        aria-hidden
        className="size-4 animate-spin rounded-full border-2 border-white/25 border-t-white"
      />
      {label}
    </span>
  );
}

/** A thin bar sliding along under the controls while results are on their way. */
function ProgressBar() {
  return (
    <div aria-hidden className="relative mt-2 h-0.5 overflow-hidden rounded bg-white/10">
      <div className="absolute inset-y-0 w-1/3 animate-[search-progress_1.1s_ease-in-out_infinite] rounded bg-brand" />
    </div>
  );
}

/** Placeholder cards until the first results are there. */
export function Skeleton() {
  return (
    <div aria-hidden className={GRID}>
      {Array.from({ length: 12 }, (_, i) => (
        <div key={i}>
          <div className="aspect-[2/3] animate-pulse rounded bg-surface-raised" />
          <div className="mt-2 h-3 w-3/4 animate-pulse rounded bg-surface-raised" />
        </div>
      ))}
    </div>
  );
}
