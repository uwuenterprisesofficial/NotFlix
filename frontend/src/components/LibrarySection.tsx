"use client";

import { useLayoutEffect, useRef, useState } from "react";
import type { AnimeCard as AnimeCardType } from "@/lib/types";
import { AnimeCard } from "./AnimeCard";
import { useT } from "./I18nProvider";

/**
 * A My List section: one row of cards (as many as fit the width), expandable to all of them.
 * Collapsed, the grid keeps its first row and gives the others no height.
 */
export function LibrarySection({
  id,
  title,
  empty,
  items,
  pending = false,
  pendingLabel,
}: {
  id: string;
  title: string;
  empty: string;
  items: AnimeCardType[];
  pending?: boolean;
  pendingLabel?: string;
}) {
  const { t } = useT();
  const grid = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [more, setMore] = useState(false); // cards beyond the first row

  useLayoutEffect(() => {
    const el = grid.current;
    if (!el || open) return;
    const measure = () => setMore(el.scrollHeight > el.clientHeight + 1);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [open, items.length]);

  return (
    <section id={id} className="mt-10">
      <h2 className="flex flex-wrap items-center gap-3 text-xl font-bold">
        {title}
        {items.length > 0 && (
          <span className="text-sm font-normal text-muted">{items.length}</span>
        )}
        {pending && (
          <span role="status" className="flex items-center gap-2 text-sm font-normal text-muted">
            <span
              aria-hidden
              className="size-4 animate-spin rounded-full border-2 border-white/25 border-t-white"
            />
            {pendingLabel}
          </span>
        )}
        {(more || open) && (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={`${id}-cards`}
            onClick={() => setOpen((o) => !o)}
            className="ml-auto text-sm font-normal text-muted hover:text-white"
          >
            {open ? t("library.showLess") : t("library.showAll", { count: items.length })}
          </button>
        )}
      </h2>
      {items.length === 0 ? (
        !pending && <p className="mt-3 text-sm text-muted">{empty}</p>
      ) : (
        <div
          id={`${id}-cards`}
          ref={grid}
          className={`mt-4 grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-x-3 md:grid-cols-[repeat(auto-fill,minmax(11rem,1fr))] ${open ? "" : "grid-rows-[auto] auto-rows-[0] overflow-hidden"}`}
        >
          {items.map((anime) => (
            <div key={anime.id} className="pb-6">
              <AnimeCard anime={anime} fluid />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
