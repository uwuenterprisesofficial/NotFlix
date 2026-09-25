import type { Metadata } from "next";
import { StatsView } from "@/components/stats/StatsView";
import { apiOrNull } from "@/lib/api";
import type { Me } from "@/lib/types";

export const metadata: Metadata = { title: "Statistics · NotFlix" };

export default async function StatsPage() {
  const me = await apiOrNull<Me>("/me");
  if (!me) {
    return (
      <div className="mx-auto mt-40 max-w-lg rounded-lg bg-surface-raised p-8 text-center">
        <h1 className="text-2xl font-bold">Statistics</h1>
        <p className="mt-3 text-muted">
          Sign in with MyAnimeList to see statistics about your list.
        </p>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-6xl px-4 pt-24 pb-16 md:px-12">
      <header className="mb-10">
        <h1 className="text-3xl font-black md:text-4xl">Your anime statistics</h1>
        <p className="mt-1 text-muted">
          From your MyAnimeList list, compared with MAL&apos;s community scores.
        </p>
      </header>
      {/* Loaded in the browser: the statistics are computed in the background. */}
      <StatsView />
    </div>
  );
}
