/** The search page's state, all in its URL (/search?q=&genre=&order=&page=). */

export const ORDERS = ["score", "popularity", "newest", "for_you"] as const;
export type Order = (typeof ORDERS)[number];

export type SearchQuery = { q: string; genre: number | null; order: Order; page: number };

export function readQuery(params: URLSearchParams): SearchQuery {
  const q = (params.get("q") ?? "").trim().slice(0, 100);
  const genre = /^\d+$/.test(params.get("genre") ?? "") ? Number(params.get("genre")) : null;
  const order = ORDERS.find((o) => o === params.get("order")) ?? "score";
  const page = Math.max(1, Math.min(200, Number(params.get("page")) || 1));
  return { q, genre, order, page };
}

export function searchHref({ q, genre, order, page }: Partial<SearchQuery>): string {
  const query = new URLSearchParams();
  if (q) query.set("q", q);
  if (genre) query.set("genre", String(genre));
  if (order && order !== "score") query.set("order", order);
  if (page && page > 1) query.set("page", String(page));
  const text = query.toString();
  return text ? `/search?${text}` : "/search";
}
