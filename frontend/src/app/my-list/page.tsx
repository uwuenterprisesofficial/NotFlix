import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";
import { LibrarySection } from "@/components/LibrarySection";
import { FriendRecommendationList } from "@/components/friends/FriendRecommendationList";
import { Prefetch } from "@/components/Prefetch";
import { RefreshWhilePending } from "@/components/RefreshWhilePending";
import { ApiError, api, apiOrNull } from "@/lib/api";
import type { MessageKey } from "@/lib/i18n";
import { getT } from "@/lib/i18n/server";
import { prefetchShows } from "@/lib/prefetch";
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
  related_upcoming: { title: "library.relatedUpcoming", empty: "library.relatedUpcomingEmpty" },
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
      <Prefetch
        shows={prefetchShows([
          ...library.sections.flatMap((s) => s.items),
          ...(fromFriends?.received.map((r) => r.anime) ?? []),
        ])}
      />
      {/* Friends' recommendations first; only sent ones after the list. */}
      {fromFriends && fromFriends.received.length > 0 && (
        <FriendRecommendationList data={fromFriends} />
      )}
      {library.sections.map((section) => {
        const labels = SECTIONS[section.id];
        if (!labels) return null;
        return (
          <LibrarySection
            key={section.id}
            id={section.id}
            title={t(labels.title)}
            empty={t(labels.empty)}
            items={section.items}
            pending={section.id.startsWith("related") && library.related_pending}
            pendingLabel={t("library.relatedLoading")}
          />
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
