import { AnimeRow } from "@/components/AnimeRow";
import { Hero } from "@/components/Hero";
import { api } from "@/lib/api";
import type { T } from "@/lib/i18n";
import { getT } from "@/lib/i18n/server";
import type { BrowseResponse } from "@/lib/types";

export default async function Home() {
  const [browse, { t }] = await Promise.all([api<BrowseResponse>("/browse"), getT()]);

  return (
    <div className="pb-16">
      {browse.hero ? <Hero anime={browse.hero} /> : <div className="h-24" />}
      <div className="relative z-10 -mt-12 space-y-6">
        {browse.rows.map((row) => (
          <AnimeRow key={row.id} row={row} />
        ))}
      </div>
      {browse.rows.length === 0 && <EmptyState browse={browse} t={t} />}
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
