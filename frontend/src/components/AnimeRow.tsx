"use client";

import { useRef } from "react";
import type { Row } from "@/lib/types";
import { AnimeCard } from "./AnimeCard";

export function AnimeRow({ row }: { row: Row }) {
  const scroller = useRef<HTMLDivElement>(null);

  function scroll(direction: 1 | -1) {
    const el = scroller.current;
    if (el) el.scrollBy({ left: direction * el.clientWidth * 0.8, behavior: "smooth" });
  }

  return (
    <section id={row.id} className="group/row relative scroll-mt-20">
      <h2 className="mb-2 px-4 text-lg font-semibold md:px-12 md:text-xl">{row.title}</h2>
      <div
        ref={scroller}
        className="no-scrollbar flex gap-2 overflow-x-auto scroll-smooth px-4 py-4 md:px-12"
      >
        {row.items.map((anime) => (
          <AnimeCard key={anime.id} anime={anime} />
        ))}
      </div>
      {[-1, 1].map((dir) => (
        <button
          key={dir}
          aria-label={dir < 0 ? "Scroll left" : "Scroll right"}
          onClick={() => scroll(dir as 1 | -1)}
          className={`absolute top-10 bottom-4 z-20 hidden w-10 bg-black/50 text-3xl opacity-0 transition-opacity group-hover/row:opacity-100 hover:bg-black/70 md:block ${dir < 0 ? "left-0" : "right-0"}`}
        >
          {dir < 0 ? "‹" : "›"}
        </button>
      ))}
    </section>
  );
}
