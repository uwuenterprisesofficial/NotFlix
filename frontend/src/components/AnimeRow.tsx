"use client";

import Link from "next/link";
import { useRef } from "react";
import type { MessageKey } from "@/lib/i18n";
import { seriesWatchHref, type SeriesProgress } from "@/lib/series";
import type { Row } from "@/lib/types";
import { AnimeCard, type PairNames } from "./AnimeCard";
import { useT } from "./I18nProvider";
import { SeriesCard } from "./series/SeriesCard";

// Row ids the backend sends, with their translated titles.
const ROW_TITLES = new Set([
  "row.continue",
  "row.from-friends",
  "row.guilty",
  "row.recommended",
  "row.my-list",
  "row.watch-again",
  "row.airing",
  "row.bypopularity",
  "row.upcoming",
  "row.new-episodes",
]);

export function AnimeRow({
  row,
  pairNames,
  series = [],
}: {
  row: Row;
  pairNames?: PairNames;
  /** Series without a MyAnimeList id the user is watching (Continue Watching only). */
  series?: SeriesProgress[];
}) {
  const { t } = useT();
  const scroller = useRef<HTMLDivElement>(null);
  const key = `row.${row.id}`;
  // Rows with a pair (Watch Together) come with their titles translated already.
  const title = ROW_TITLES.has(key) && !pairNames ? t(key as MessageKey) : row.title;

  function scroll(direction: 1 | -1) {
    const el = scroller.current;
    if (el) el.scrollBy({ left: direction * el.clientWidth * 0.8, behavior: "smooth" });
  }

  return (
    <section id={row.id} className="group/row relative scroll-mt-20">
      <div className="mb-2 flex items-baseline gap-4 px-4 md:px-12">
        <h2 className="text-lg font-semibold md:text-xl">{title}</h2>
        {row.id === "new-episodes" && (
          <Link href="/calendar" className="text-sm text-muted hover:text-white">
            {t("row.calendar")}
          </Link>
        )}
        {(row.id === "my-list" || row.id === "continue") && (
          <Link href="/my-list" className="text-sm text-muted hover:text-white">
            {t("row.allOfMyList")}
          </Link>
        )}
      </div>
      <div
        ref={scroller}
        className="no-scrollbar flex gap-2 overflow-x-auto scroll-smooth px-4 py-4 md:px-12"
      >
        {series.map((s) => (
          <SeriesCard
            key={s.slug}
            href={seriesWatchHref(s.slug, s.season, s.episode)}
            title={s.title}
            image={s.image_url}
            badge={t("series.card", { season: s.season, episode: s.episode })}
          />
        ))}
        {row.items.map((anime) => (
          <AnimeCard key={anime.id} anime={anime} pairNames={pairNames} />
        ))}
      </div>
      {[-1, 1].map((dir) => (
        <button
          key={dir}
          aria-label={dir < 0 ? t("row.scrollLeft") : t("row.scrollRight")}
          onClick={() => scroll(dir as 1 | -1)}
          className={`absolute top-10 bottom-4 z-20 hidden w-10 bg-black/50 text-3xl opacity-0 transition-opacity group-hover/row:opacity-100 hover:bg-black/70 md:block ${dir < 0 ? "left-0" : "right-0"}`}
        >
          {dir < 0 ? "‹" : "›"}
        </button>
      ))}
    </section>
  );
}
