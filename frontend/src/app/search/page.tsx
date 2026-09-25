import type { Metadata } from "next";
import Link from "next/link";
import { AnimeCard } from "@/components/AnimeCard";
import { SearchControls } from "@/components/SearchControls";
import { api } from "@/lib/api";
import type { Genre, SearchResponse } from "@/lib/types";

export const metadata: Metadata = { title: "Search · NotFlix" };

const ORDERS = ["score", "popularity", "newest", "for_you"] as const;
type Order = (typeof ORDERS)[number];

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

export default async function SearchPage({ searchParams }: PageProps<"/search">) {
  const params = await searchParams;
  const q = one(params.q).slice(0, 100);
  const genreId = /^\d+$/.test(one(params.genre)) ? Number(one(params.genre)) : null;
  const order: Order = ORDERS.find((o) => o === one(params.order)) ?? "score";
  const page = Math.max(1, Math.min(200, Number(one(params.page)) || 1));

  const genres = await api<Genre[]>("/genres");
  const genre = genres.find((g) => g.id === genreId) ?? null;

  let result: SearchResponse | null = null;
  if (q) {
    result = await api<SearchResponse>(`/search?${new URLSearchParams({ q, page: String(page) })}`);
    // MAL's search can't filter by genre: narrow this page down to it.
    if (genre) result.items = result.items.filter((a) => a.genres.includes(genre.name));
  } else if (genre) {
    const apiOrder = order === "for_you" ? "score" : order;
    result = await api<SearchResponse>(
      `/search/genre/${genre.id}?${new URLSearchParams({ order: apiOrder, page: String(page) })}`,
    );
  }
  if (result && order === "for_you") {
    result.items.sort((a, b) => (b.prediction?.score ?? 0) - (a.prediction?.score ?? 0));
  }

  const link = (p: number) => {
    const query = new URLSearchParams();
    if (q) query.set("q", q);
    if (genre) query.set("genre", String(genre.id));
    if (order !== "score") query.set("order", order);
    query.set("page", String(p));
    return `/search?${query}`;
  };

  return (
    <div className="px-4 pt-24 pb-16 md:px-12">
      <h1 className="text-3xl font-black">Search</h1>
      <SearchControls q={q} genreId={genre?.id ?? null} order={order} genres={genres} />

      {result === null ? (
        <p className="mt-10 text-muted">
          Search MyAnimeList by title, or pick a genre, theme or demographic to browse.
        </p>
      ) : (
        <>
          <p className="mt-6 text-sm text-muted">
            {heading(q, genre)}
            {result.source === "local" && " · from shows NotFlix already knows"}
          </p>
          {result.items.length === 0 ? (
            <p className="mt-10 text-muted">Nothing found.</p>
          ) : (
            <div className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-x-3 gap-y-6 md:grid-cols-[repeat(auto-fill,minmax(11rem,1fr))]">
              {result.items.map((anime) => (
                <div key={anime.id}>
                  <AnimeCard anime={anime} fluid />
                </div>
              ))}
            </div>
          )}
          <nav className="mt-10 flex items-center justify-center gap-4 text-sm">
            {page > 1 && (
              <Link
                href={link(page - 1)}
                className="rounded bg-surface-raised px-4 py-2 hover:bg-white/10"
              >
                ‹ Previous
              </Link>
            )}
            <span className="text-muted">Page {page}</span>
            {result.has_next && (
              <Link
                href={link(page + 1)}
                className="rounded bg-surface-raised px-4 py-2 hover:bg-white/10"
              >
                Next ›
              </Link>
            )}
          </nav>
        </>
      )}
    </div>
  );
}

function heading(q: string, genre: Genre | null) {
  const what = q ? `Results for “${q}”` : `${genre!.name}`;
  const within = q && genre ? ` in ${genre.name}` : "";
  return `${what}${within}`;
}
