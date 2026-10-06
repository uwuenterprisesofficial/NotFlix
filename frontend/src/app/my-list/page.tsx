import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { AnimeCard } from "@/components/AnimeCard";
import { FriendRecommendationList } from "@/components/friends/FriendRecommendationList";
import { RefreshWhilePending } from "@/components/RefreshWhilePending";
import { ApiError, api, apiOrNull } from "@/lib/api";
import type { MessageKey } from "@/lib/i18n";
import { getT } from "@/lib/i18n/server";
import type { FriendRecommendations, Row } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("nav.myList")} · NotFlix` };
}

type Library = { sections: Row[]; related_pending: boolean };

const SECTIONS: Record<string, { title: MessageKey; empty: MessageKey }> = {
  continue: { title: "library.continue", empty: "library.continueEmpty" },
  season: { title: "library.season", empty: "library.seasonEmpty" },
  planned: { title: "library.planned", empty: "library.plannedEmpty" },
  related: { title: "library.related", empty: "library.relatedEmpty" },
};

/** The user's list as a page: what they're watching, what of it airs this season, what they
 * plan to watch, and what's related to what they watched (and isn't on their list yet). */
export default async function MyListPage() {
  const { t } = await getT();
  let library: Library;
  let fromFriends: FriendRecommendations | null;
  try {
    [library, fromFriends] = await Promise.all([
      api<Library>("/me/library"),
      apiOrNull<FriendRecommendations>("/friends/recommendations").catch(() => null),
    ]);
  } catch (e) {
    // Not signed in (or a guest without a list).
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) redirect("/login");
    throw e;
  }

  return (
    <div className="px-4 pt-24 pb-16 md:px-12">
      <h1 className="text-3xl font-black">{t("nav.myList")}</h1>
      {library.related_pending && <RefreshWhilePending />}
      {/* Friends' recommendations first; only sent ones after the list. */}
      {fromFriends && fromFriends.received.length > 0 && (
        <FriendRecommendationList data={fromFriends} />
      )}
      {library.sections.map((section) => {
        const labels = SECTIONS[section.id];
        if (!labels) return null;
        const pending = section.id === "related" && library.related_pending;
        return (
          <section key={section.id} id={section.id} className="mt-10">
            <h2 className="flex items-center gap-3 text-xl font-bold">
              {t(labels.title)}
              {section.items.length > 0 && (
                <span className="text-sm font-normal text-muted">{section.items.length}</span>
              )}
              {pending && (
                <span role="status" className="flex items-center gap-2 text-sm font-normal text-muted">
                  <span
                    aria-hidden
                    className="size-4 animate-spin rounded-full border-2 border-white/25 border-t-white"
                  />
                  {t("library.relatedLoading")}
                </span>
              )}
            </h2>
            {section.items.length === 0 ? (
              !pending && <p className="mt-3 text-sm text-muted">{t(labels.empty)}</p>
            ) : (
              <div className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-x-3 gap-y-6 md:grid-cols-[repeat(auto-fill,minmax(11rem,1fr))]">
                {section.items.map((anime) => (
                  <div key={anime.id}>
                    <AnimeCard anime={anime} fluid />
                  </div>
                ))}
              </div>
            )}
          </section>
        );
      })}
      <p className="mt-12 text-sm text-muted">
        {t("library.searchMore")}{" "}
        <Link href="/search" className="underline hover:text-white">
          {t("nav.search")}
        </Link>
      </p>
      {fromFriends && fromFriends.received.length === 0 && (
        <FriendRecommendationList data={fromFriends} />
      )}
    </div>
  );
}
