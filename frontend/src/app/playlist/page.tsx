import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { PlaylistEditor } from "@/components/playlist/PlaylistEditor";
import { Prefetch } from "@/components/Prefetch";
import { ApiError, api } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import { prefetchShows } from "@/lib/prefetch";
import type { Playlist } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("playlist.title")} · NotFlix` };
}

/** The shows that play next, in the user's order (see the backend's services/playlist.py). */
export default async function PlaylistPage() {
  const { t } = await getT();
  let playlist: Playlist;
  try {
    playlist = await api<Playlist>("/me/playlist");
  } catch (e) {
    // Not signed in (or a guest without a list).
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) redirect("/login");
    throw e;
  }
  return (
    <div className="mx-auto max-w-4xl px-4 pt-24 pb-16">
      <h1 className="text-3xl font-black md:text-4xl">{t("playlist.title")}</h1>
      <p className="mt-1 text-muted">{t("playlist.subtitle")}</p>
      {/* Their streams are looked for in the background, so they start at once. */}
      <Prefetch shows={prefetchShows(playlist.items.map((i) => i.anime))} />
      <PlaylistEditor initial={playlist} />
    </div>
  );
}
