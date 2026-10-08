/** The search page's state, all in its URL (/search?q=&genre=&order=&page=&filters). */

export const ORDERS = ["score", "popularity", "newest", "for_you"] as const;
export type Order = (typeof ORDERS)[number];

/** Narrowing the results down: hide what's been seen, MAL's score and the predicted score. */
export type Filters = {
  hideSeen: boolean;
  minScore: number | null;
  maxScore: number | null;
  minPredicted: number | null;
  maxPredicted: number | null;
};

export type SearchQuery = {
  q: string;
  genre: number | null;
  order: Order;
  page: number;
  /** Only shows with a dub (in the UI's language) that NotFlix has found streams of. */
  dub: boolean;
} & Filters;

const SCORE_PARAMS = {
  minScore: "min_score",
  maxScore: "max_score",
  minPredicted: "min_predicted",
  maxPredicted: "max_predicted",
} as const;

function score(value: string | null): number | null {
  if (value === null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 && n <= 10 ? n : null;
}

export function readQuery(params: URLSearchParams): SearchQuery {
  const q = (params.get("q") ?? "").trim().slice(0, 100);
  const genre = /^\d+$/.test(params.get("genre") ?? "") ? Number(params.get("genre")) : null;
  const order = ORDERS.find((o) => o === params.get("order")) ?? "score";
  const page = Math.max(1, Math.min(200, Number(params.get("page")) || 1));
  return {
    q,
    genre,
    order,
    page,
    dub: params.get("dub") === "1",
    hideSeen: params.get("hide_seen") === "1",
    minScore: score(params.get("min_score")),
    maxScore: score(params.get("max_score")),
    minPredicted: score(params.get("min_predicted")),
    maxPredicted: score(params.get("max_predicted")),
  };
}

/** The filters as the API's query parameters. */
export function filterParams(f: Filters): Record<string, string> {
  const out: Record<string, string> = {};
  if (f.hideSeen) out.hide_seen = "true";
  for (const [key, param] of Object.entries(SCORE_PARAMS)) {
    const value = f[key as keyof typeof SCORE_PARAMS];
    if (value !== null) out[param] = String(value);
  }
  return out;
}

export function hasFilters(f: Filters): boolean {
  return Object.keys(filterParams(f)).length > 0;
}

export function searchHref(query: Partial<SearchQuery>): string {
  const { q, genre, order, page, dub } = query;
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (genre) params.set("genre", String(genre));
  if (dub) params.set("dub", "1");
  if (query.hideSeen) params.set("hide_seen", "1");
  for (const [key, param] of Object.entries(SCORE_PARAMS)) {
    const value = query[key as keyof typeof SCORE_PARAMS];
    if (value !== null && value !== undefined) params.set(param, String(value));
  }
  if (order && order !== "score") params.set("order", order);
  if (page && page > 1) params.set("page", String(page));
  const text = params.toString();
  return text ? `/search?${text}` : "/search";
}
