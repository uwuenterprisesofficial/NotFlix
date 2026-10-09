import { AnimeRow } from "@/components/AnimeRow";
import { Hero } from "@/components/Hero";
import { ImportingList } from "@/components/ImportingList";
import { Prefetch } from "@/components/Prefetch";
import { api, apiOrNull } from "@/lib/api";
import type { SeriesProgress } from "@/lib/series";
import type { T } from "@/lib/i18n";
import { prefetchShows } from "@/lib/prefetch";
import { getT } from "@/lib/i18n/server";
import type { BrowseResponse } from "@/lib/types";

export default async function Home() {
  const [browse, { t }, series] = await Promise.all([
    api<BrowseResponse>("/browse"),
    getT(),
    // Series without a MyAnimeList id the user is in the middle of (signed in only).
    apiOrNull<SeriesProgress[]>("/series/progress").catch(() => null),
  ]);
  // They go in Continue Watching, which is only there when there are shows to continue.
  const watching = series ?? [];
  if (watching.length && !browse.rows.some((r) => r.id === "continue")) {
    browse.rows.unshift({ id: "continue", title: "Continue Watching", items: [] });
  }

  const empty = browse.rows.length === 0;
  return (
    <div className="pb-16">
      {browse.hero ? <Hero anime={browse.hero} /> : <div className="h-24" />}
      <Prefetch shows={prefetchShows([browse.hero, ...browse.rows.flatMap((r) => r.items)])} />
      {browse.syncing && !empty && <ImportingList empty={false} />}
      <div className="relative z-10 -mt-12 space-y-6">
        {browse.rows.map((row) => (
          <AnimeRow key={row.id} row={row} series={row.id === "continue" ? watching : []} />
        ))}
      </div>
      {empty && (browse.syncing ? <ImportingList empty /> : <EmptyState browse={browse} t={t} />)}
    </div>
  );
}

function EmptyState({ browse, t }: { browse: BrowseResponse; t: T }) {
  let title = t("home.emptyTitle");
  let body = t("home.emptyBody");
  if (!browse.mal_configured) {
    title = t("home.connectTitle");
    body = t("home.connectBody");
  } else if (!browse.signed_in) {
    body = t("home.signInBody");
  }

  return (
    <div className="mx-auto mt-24 max-w-lg rounded-lg bg-surface-raised p-8 text-center">
      <h2 className="text-2xl font-bold">{title}</h2>
      <p className="mt-3 text-muted">{body}</p>
    </div>
  );
}
