"use client";

import Image from "next/image";
import Link from "next/link";
import { displayTitle, reasonText, relativeTime } from "@/lib/format";
import { formatNumber, genreName } from "@/lib/i18n";
import type { AnimeCard as AnimeCardType } from "@/lib/types";
import { useNow } from "@/lib/useNow";
import { useT } from "./I18nProvider";
import { PredictionBadge } from "./PredictionBadge";
import { allowedImage } from "@/lib/images";

export function AnimeCard({ anime, fluid = false }: { anime: AnimeCardType; fluid?: boolean }) {
  const { t, lang } = useT();
  const now = useNow();
  const airing = anime.airing;
  // New Episodes: the (released) episode opens the player directly.
  const href = airing ? `/watch/${anime.id}/${airing.episode}` : `/anime/${anime.id}`;
  const watched = anime.progress?.episodes_watched ?? 0;
  const showProgress = anime.progress?.status === "watching" && anime.num_episodes;
  const title = displayTitle(anime);

  return (
    <Link
      href={href}
      className={`group/card relative block shrink-0 transition-transform duration-200 hover:z-10 hover:scale-110 ${fluid ? "w-full" : "w-36 md:w-44"}`}
      title={anime.reason ? reasonText(t, anime.reason) : title}
    >
      <div className="relative aspect-[2/3] overflow-hidden rounded-md bg-surface-raised">
        {allowedImage(anime.picture_url) ? (
          <Image
            src={allowedImage(anime.picture_url)!}
            alt={title}
            fill
            sizes={fluid ? "(min-width: 768px) 220px, 180px" : "(min-width: 768px) 176px, 144px"}
            className="object-cover"
          />
        ) : (
          <span className="grid h-full place-items-center p-2 text-center text-sm">{title}</span>
        )}
        <div className="absolute top-1.5 left-1.5">
          <PredictionBadge prediction={anime.prediction} />
        </div>
        {airing && (
          <span className="absolute right-1.5 bottom-1.5 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-semibold shadow">
            {t("airing.episode", { episode: airing.episode })}
            {now !== null && (
              <span className="font-normal text-neutral-300">
                {" · "}
                {relativeTime(lang, airing.airing_at, now)}
              </span>
            )}
          </span>
        )}
        <div className="absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/90 via-black/20 to-transparent p-2 opacity-0 transition-opacity group-hover/card:opacity-100">
          <p className="line-clamp-2 text-sm font-semibold">{title}</p>
          <p className="text-xs text-muted">
            {anime.mean ? `★ ${formatNumber(lang, anime.mean)}` : ""}{" "}
            {anime.genres
              .slice(0, 2)
              .map((g) => genreName(lang, g))
              .join(" · ")}
          </p>
        </div>
      </div>
      {showProgress ? (
        <div className="mt-1 h-1 overflow-hidden rounded bg-white/20">
          <div
            className="h-full bg-brand"
            style={{ width: `${Math.min(100, (watched / anime.num_episodes!) * 100)}%` }}
          />
        </div>
      ) : null}
    </Link>
  );
}
