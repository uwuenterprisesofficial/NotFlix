"use client";

import Link from "next/link";

/** A series as a poster card (the same shape as the anime cards): its picture, or its title. */
export function SeriesCard({
  href,
  title,
  image,
  badge,
  tag,
  fluid = false,
}: {
  href: string;
  title: string;
  image?: string | null;
  /** Shown in the corner, e.g. the episode to continue with. */
  badge?: string;
  /** A label in the top corner, e.g. "Series" among anime. */
  tag?: string;
  fluid?: boolean;
}) {
  return (
    <Link
      href={href}
      title={title}
      className={`group/card relative block shrink-0 transition duration-200 hover:brightness-110 ${fluid ? "w-full" : "w-36 md:w-44"}`}
    >
      <div className="relative aspect-[2/3] overflow-hidden rounded-md bg-surface-raised">
        {image ? (
          // eslint-disable-next-line @next/next/no-img-element -- the site's own pictures, from a host next/image doesn't list
          <img
            src={image}
            alt={title}
            loading="lazy"
            referrerPolicy="no-referrer"
            className="absolute inset-0 size-full object-cover"
          />
        ) : (
          <span className="grid h-full place-items-center p-2 text-center text-sm">{title}</span>
        )}
        {tag && (
          <span className="absolute top-1.5 left-1.5 rounded bg-black/80 px-1.5 py-0.5 text-[10px] font-bold tracking-wide uppercase shadow">
            {tag}
          </span>
        )}
        {badge && (
          <span className="absolute right-1.5 bottom-1.5 rounded bg-black/80 px-1.5 py-0.5 text-[11px] font-semibold shadow">
            ▶ {badge}
          </span>
        )}
        <div className="absolute inset-0 flex flex-col justify-end bg-gradient-to-t from-black/90 via-black/20 to-transparent p-2 opacity-0 transition-opacity group-hover/card:opacity-100">
          <p className="line-clamp-2 text-sm font-semibold">{title}</p>
        </div>
      </div>
    </Link>
  );
}
