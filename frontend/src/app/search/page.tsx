import type { Metadata } from "next";
import { Suspense } from "react";
import { SearchControls } from "@/components/SearchControls";
import { SearchResults, Skeleton } from "@/components/SearchResults";
import { api } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import type { Genre } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("nav.search")} · NotFlix` };
}

// The page itself only needs the genre list (which the backend answers without waiting for
// anything): results are fetched in the browser, the quick ones first, so it opens at once.
export default async function SearchPage() {
  const [genres, { t }] = await Promise.all([api<Genre[]>("/genres").catch(() => []), getT()]);
  return (
    <div className="px-4 pt-24 pb-16 md:px-12">
      <h1 className="text-3xl font-black">{t("search.title")}</h1>
      <Suspense fallback={<Skeleton />}>
        <SearchControls genres={genres} />
        <SearchResults genres={genres} />
      </Suspense>
    </div>
  );
}
