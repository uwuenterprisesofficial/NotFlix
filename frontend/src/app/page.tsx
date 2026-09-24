import { AnimeRow } from "@/components/AnimeRow";
import { Hero } from "@/components/Hero";
import { api } from "@/lib/api";
import type { BrowseResponse } from "@/lib/types";

export default async function Home() {
  const browse = await api<BrowseResponse>("/browse");

  return (
    <div className="pb-16">
      {browse.hero ? <Hero anime={browse.hero} /> : <div className="h-24" />}
      <div className="relative z-10 -mt-12 space-y-6">
        {browse.rows.map((row) => (
          <AnimeRow key={row.id} row={row} />
        ))}
      </div>
      {browse.rows.length === 0 && <EmptyState browse={browse} />}
    </div>
  );
}

function EmptyState({ browse }: { browse: BrowseResponse }) {
  let title = "Nothing here yet";
  let body = "Press “Sync MAL” to import your MyAnimeList list and build recommendations.";
  if (!browse.mal_configured) {
    title = "Connect MyAnimeList";
    body =
      "Create an API client at myanimelist.net/apiconfig, then set MAL_CLIENT_ID and MAL_CLIENT_SECRET in .env and restart the backend.";
  } else if (!browse.signed_in) {
    body = "Sign in with MyAnimeList to see your list and personal recommendations.";
  }

  return (
    <div className="mx-auto mt-24 max-w-lg rounded-lg bg-surface-raised p-8 text-center">
      <h2 className="text-2xl font-bold">{title}</h2>
      <p className="mt-3 text-muted">{body}</p>
    </div>
  );
}
