"use client";

import { useState } from "react";
import type { AnimeCard as Card } from "@/lib/types";
import { AnimeCard } from "../AnimeCard";
import { useT } from "../I18nProvider";

type Show = "all" | "unwatched" | "watched";
type Sort = "popularity" | "score" | "for_you";

/** Every show of the season: the watched ones marked (greyed, ✓), to see what's left. */
export function SeasonList({ items, signedIn }: { items: Card[]; signedIn: boolean }) {
  const { t } = useT();
  const [show, setShow] = useState<Show>("all");
  const [sort, setSort] = useState<Sort>("popularity");
  let shown = items.filter((a) =>
    show === "all" ? true : show === "watched" ? a.caught_up : !a.caught_up,
  );
  if (sort === "score") shown = [...shown].sort((a, b) => (b.mean ?? 0) - (a.mean ?? 0));
  if (sort === "for_you")
    shown = [...shown].sort(
      (a, b) =>
        (b.prediction?.score ?? b.progress?.score ?? 0) -
        (a.prediction?.score ?? a.progress?.score ?? 0),
    );
  const button = (active: boolean) =>
    `rounded px-3 py-1 text-sm ${active ? "bg-white font-semibold text-black" : "bg-surface-raised hover:bg-white/15"}`;

  return (
    <section className="mt-10 px-4 md:px-12">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="mr-4 text-lg font-semibold md:text-xl">
          {t("seasons.all", { n: items.length })}
        </h2>
        {signedIn &&
          (["all", "unwatched", "watched"] as const).map((s) => (
            <button key={s} onClick={() => setShow(s)} className={button(show === s)}>
              {t(`seasons.show.${s}`)}
            </button>
          ))}
        <select
          aria-label={t("search.order")}
          value={sort}
          onChange={(e) => setSort(e.target.value as Sort)}
          className="ml-auto rounded border border-white/20 bg-surface-raised px-3 py-1.5 text-sm"
        >
          <option value="popularity">{t("search.orderPopularity")}</option>
          <option value="score">{t("search.orderScore")}</option>
          {signedIn && <option value="for_you">{t("search.orderForYou")}</option>}
        </select>
      </div>
      <div className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-x-3 gap-y-6 md:grid-cols-[repeat(auto-fill,minmax(11rem,1fr))]">
        {shown.map((anime) => (
          <div key={anime.id}>
            <AnimeCard anime={anime} fluid />
          </div>
        ))}
      </div>
    </section>
  );
}
