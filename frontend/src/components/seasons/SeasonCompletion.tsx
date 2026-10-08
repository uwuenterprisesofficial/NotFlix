"use client";

import { formatNumber, genreName } from "@/lib/i18n";
import type { Season } from "@/lib/types";
import { useT } from "../I18nProvider";

const MIN_GENRE = 3; // genres with fewer shows make no facts
const BARS = 10;

/** "12 of 48 watched", and fun facts about the season's genres. */
export function SeasonCompletion({
  completion,
  genres,
}: {
  completion: Season["completion"];
  genres: Season["genres"];
}) {
  const { t, lang } = useT();
  if (!completion) return null;
  const pct = (watched: number, total: number) => Math.round((watched / Math.max(1, total)) * 100);
  const name = (genre: string) => genreName(lang, genre);

  const facts: string[] = [];
  const sizable = genres.filter((g) => g.total >= MIN_GENRE);
  const best = [...sizable].sort(
    (a, b) => b.watched / b.total - a.watched / a.total || b.total - a.total,
  )[0];
  if (best && best.watched > 0)
    facts.push(
      t("seasons.fact.best", { pct: pct(best.watched, best.total), genre: name(best.genre) }),
    );
  const all = sizable.find((g) => g.watched === g.total && g !== best);
  if (all) facts.push(t("seasons.fact.all", { genre: name(all.genre), n: all.total }));
  if (genres[0])
    facts.push(t("seasons.fact.biggest", { genre: name(genres[0].genre), n: genres[0].total }));
  const untouched = sizable.filter((g) => g.watched === 0).sort((a, b) => b.total - a.total)[0];
  if (untouched)
    facts.push(t("seasons.fact.untouched", { genre: name(untouched.genre), n: untouched.total }));

  const done = pct(completion.watched, completion.total);
  return (
    <section className="mt-6 grid gap-4 px-4 md:grid-cols-[minmax(0,20rem)_1fr] md:px-12">
      <div className="rounded-lg bg-surface-raised p-4">
        <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">
          {t("seasons.completion")}
        </h2>
        <p className="mt-2 text-3xl font-black">
          {formatNumber(lang, completion.watched)}
          <span className="text-lg font-semibold text-muted">
            {" "}
            / {formatNumber(lang, completion.total)}
          </span>
        </p>
        <p className="text-sm text-muted">{t("seasons.watchedOf", { pct: done })}</p>
        <div className="mt-3 h-2 overflow-hidden rounded bg-white/15">
          <div className="h-full bg-brand" style={{ width: `${done}%` }} />
        </div>
        <p className="mt-3 text-sm text-muted">
          {t("seasons.watchingPlanned", {
            watching: completion.watching,
            planned: completion.planned,
          })}
        </p>
        {facts.length > 0 && (
          <ul className="mt-4 space-y-1.5 text-sm">
            {facts.map((fact) => (
              <li key={fact} className="flex gap-2">
                <span aria-hidden>✦</span>
                {fact}
              </li>
            ))}
          </ul>
        )}
      </div>
      <div className="rounded-lg bg-surface-raised p-4">
        <h2 className="text-sm font-semibold tracking-wide text-muted uppercase">
          {t("seasons.genres")}
        </h2>
        <ul className="mt-3 space-y-2">
          {genres.slice(0, BARS).map((g) => (
            <li
              key={g.genre}
              className="grid grid-cols-[8rem_1fr_4.5rem] items-center gap-3 text-sm"
            >
              <span className="truncate">{name(g.genre)}</span>
              <span className="h-2 overflow-hidden rounded bg-white/15">
                <span
                  className="block h-full bg-brand"
                  style={{ width: `${pct(g.watched, g.total)}%` }}
                />
              </span>
              <span className="text-right text-muted tabular-nums">
                {g.watched}/{g.total}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
