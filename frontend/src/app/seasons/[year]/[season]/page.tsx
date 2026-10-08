import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AnimeRow } from "@/components/AnimeRow";
import { Prefetch } from "@/components/Prefetch";
import { SeasonCompletion } from "@/components/seasons/SeasonCompletion";
import { SeasonList } from "@/components/seasons/SeasonList";
import { SeasonPicker } from "@/components/seasons/SeasonPicker";
import { api } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import { prefetchShows } from "@/lib/prefetch";
import { SEASONS, seasonHref, stepSeason } from "@/lib/seasons";
import type { Season, SeasonName } from "@/lib/types";

function parse(year: string, season: string): { year: number; season: SeasonName } | null {
  if (!/^\d{4}$/.test(year) || !SEASONS.includes(season as SeasonName)) return null;
  return { year: Number(year), season: season as SeasonName };
}

export async function generateMetadata({
  params,
}: PageProps<"/seasons/[year]/[season]">): Promise<Metadata> {
  const { year, season } = await params;
  const p = parse(year, season);
  const { t } = await getT();
  return {
    title: `${p ? t(`season.${p.season}`, { year: p.year }) : t("nav.seasons")} · NotFlix`,
  };
}

/** Everything starting in a season: what to watch of it, and how much of it the user has seen. */
export default async function SeasonPage({ params }: PageProps<"/seasons/[year]/[season]">) {
  const { year: y, season: s } = await params;
  const p = parse(y, s);
  if (!p || p.year < 1917 || p.year > 2100) notFound();
  const [{ t }, data] = await Promise.all([getT(), api<Season>(`/seasons/${p.year}/${p.season}`)]);
  const before = stepSeason(p.year, p.season, -1);
  const after = stepSeason(p.year, p.season, 1);
  const rows = [
    { id: "season-recommended", title: t("seasons.recommended"), items: data.recommended },
    { id: "season-highlights", title: t("seasons.highlights"), items: data.highlights },
    { id: "season-underrated", title: t("seasons.underrated"), items: data.underrated },
  ].filter((r) => r.items.length);

  return (
    <div className="pt-24 pb-16">
      <header className="flex flex-wrap items-center gap-4 px-4 md:px-12">
        <Link
          href={seasonHref(before)}
          aria-label={t("seasons.previous")}
          title={t(`season.${before.season}`, { year: before.year })}
          className="grid size-10 place-items-center rounded-full bg-surface-raised text-2xl hover:bg-white/15"
        >
          ‹
        </Link>
        <h1 className="text-3xl font-black md:text-4xl">
          {t(`season.${p.season}`, { year: p.year })}
        </h1>
        <Link
          href={seasonHref(after)}
          aria-label={t("seasons.next")}
          title={t(`season.${after.season}`, { year: after.year })}
          className="grid size-10 place-items-center rounded-full bg-surface-raised text-2xl hover:bg-white/15"
        >
          ›
        </Link>
        <SeasonPicker year={p.year} season={p.season} />
        {data.current && (
          <span className="rounded bg-brand px-2 py-0.5 text-xs font-bold uppercase">
            {t("seasons.now")}
          </span>
        )}
      </header>
      {!data.complete && (
        <p className="mt-2 px-4 text-sm text-muted md:px-12">{t("seasons.incomplete")}</p>
      )}

      {data.items.length === 0 ? (
        <p className="mt-10 px-4 text-muted md:px-12">{t("seasons.nothing")}</p>
      ) : (
        <>
          <SeasonCompletion completion={data.completion} genres={data.genres} />
          <Prefetch shows={prefetchShows([...data.recommended, ...data.highlights])} />
          <div className="mt-8 space-y-6">
            {rows.map((row) => (
              <div key={row.id}>
                <AnimeRow row={row} />
                {row.id === "season-underrated" && (
                  <p className="-mt-2 px-4 text-xs text-muted md:px-12">
                    {t("seasons.underratedInfo")}
                  </p>
                )}
              </div>
            ))}
          </div>
          <SeasonList items={data.items} signedIn={data.completion !== null} />
        </>
      )}
    </div>
  );
}
