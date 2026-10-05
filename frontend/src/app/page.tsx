import { AnimeRow } from "@/components/AnimeRow";
import { Hero } from "@/components/Hero";
import { ImportingList } from "@/components/ImportingList";
import { api } from "@/lib/api";
import type { T } from "@/lib/i18n";
import { getT } from "@/lib/i18n/server";
import type { BrowseResponse } from "@/lib/types";

export default async function Home() {
  const [browse, { t }] = await Promise.all([api<BrowseResponse>("/browse"), getT()]);

  const empty = browse.rows.length === 0;
  return (
    <div className="pb-16">
      {browse.hero ? <Hero anime={browse.hero} /> : <div className="h-24" />}
      {browse.syncing && !empty && <ImportingList empty={false} />}
      <div className="relative z-10 -mt-12 space-y-6">
        {browse.rows.map((row) => (
          <AnimeRow key={row.id} row={row} />
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
