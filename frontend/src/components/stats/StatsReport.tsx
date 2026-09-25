"use client";

import Image from "next/image";
import Link from "next/link";
import { useT } from "@/components/I18nProvider";
import { PredictionBadge } from "@/components/PredictionBadge";
import { Breakdown } from "@/components/stats/Breakdown";
import { DivergingBars } from "@/components/stats/DivergingBars";
import { ScoreDistribution } from "@/components/stats/ScoreDistribution";
import { YOU } from "@/components/stats/colors";
import { displayTitle } from "@/lib/format";
import { featureName, formatNumber, type Lang, type MessageKey, type T } from "@/lib/i18n";
import type { HotTake, ShowRef, Stats, TagStat } from "@/lib/types";
import { allowedImage } from "@/lib/images";

/** Number formatting for the page's language; "–" for missing values. */
function numbers(lang: Lang) {
  const num = (v: number | null | undefined, digits = 2) =>
    v === null || v === undefined ? "–" : formatNumber(lang, v, digits);
  const signed = (v: number | null | undefined, digits = 2) =>
    v === null || v === undefined ? "–" : `${v >= 0 ? "+" : "−"}${num(Math.abs(v), digits)}`;
  return { num, signed };
}

const kindOne = (t: T, kind: string) => t(`kindOne.${kind}` as MessageKey);

/** Every section of the statistics page. */
export function StatsReport({ stats }: { stats: Stats }) {
  const { t, lang } = useT();
  const { num, signed } = numbers(lang);
  const o = stats.overview;
  if (o.total === 0) {
    return <p className="text-muted">{t("stats.syncFirst")}</p>;
  }
  const feature = (f: { key: string; name: string; kind: string; points: number }) => ({
    name: featureName(lang, f.key, f.name),
    value: f.points,
    detail: kindOne(t, f.kind),
  });
  const thresholds = stats.model?.thresholds.map((v) => num(v, 1)) ?? [];

  return (
    <div className="space-y-10">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile
          label={t("stats.shows")}
          value={formatNumber(lang, o.total)}
          note={t("stats.scored", { count: formatNumber(lang, o.scored) })}
        />
        <Tile
          label={t("stats.timeWatched")}
          value={o.days !== null ? t("stats.days", { days: num(o.days, 1) }) : "–"}
          note={t("stats.episodes", { count: formatNumber(lang, o.episodes) })}
        />
        <Tile
          label={t("stats.meanScore")}
          value={num(o.mean_score)}
          note={o.mal_mean !== null ? t("stats.malSame", { mal: num(o.mal_mean) }) : undefined}
        />
        <Tile
          label={t("stats.agreement")}
          value={num(o.agreement)}
          note={
            o.mean_abs_difference !== null
              ? t("stats.offBy", { points: num(o.mean_abs_difference, 1) })
              : undefined
          }
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <Card title={t("stats.distribution")} subtitle={t("stats.distributionInfo")}>
          <ScoreDistribution data={stats.score_distribution} />
        </Card>
        <Card
          title={t("stats.yourList")}
          subtitle={
            o.drop_rate !== null
              ? t("stats.dropRate", { rate: num(o.drop_rate * 100, 0) })
              : undefined
          }
        >
          <StatusBars stats={stats} />
          <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
            <Fact label={t("stats.median")} value={num(o.median_score, 1)} />
            <Fact label={t("stats.spread")} value={num(o.std_score)} />
            <Fact label={t("stats.vsMal")} value={signed(o.mean_difference)} />
            <Fact
              label={t("stats.members")}
              value={o.median_members !== null ? formatNumber(lang, o.median_members) : "–"}
            />
          </dl>
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card title={t("stats.favourites")} subtitle={t("stats.favouritesInfo")}>
          <TagBars items={stats.favourites} empty={t("stats.favouritesEmpty")} />
        </Card>
        <Card title={t("stats.hated")} subtitle={t("stats.hatedInfo")}>
          <TagBars items={stats.hated} empty={t("stats.hatedEmpty")} />
        </Card>
      </div>

      {stats.hot_takes.length > 0 && (
        <section>
          <h2 className="text-xl font-bold">{t("stats.hotTakes")}</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {stats.hot_takes.map((take, i) => (
              <HotTakeCard key={`${take.kind}-${i}`} take={take} />
            ))}
          </div>
        </section>
      )}

      <Card title={t("stats.breakdown")} subtitle={t("stats.breakdownInfo")}>
        <Breakdown breakdown={stats.breakdown} />
      </Card>

      {stats.model ? (
        <Card
          title={t("stats.model")}
          subtitle={t("stats.modelInfo", { count: stats.model.scored })}
        >
          <p className="text-sm text-neutral-300">
            {stats.model.mae !== null &&
              t("stats.modelError", { mae: stats.model.mae, baseline: stats.model.baseline_mae })}
            {t("stats.malWeight", { weight: num(stats.model.mal_weight ?? 0) })}
          </p>
          <div className="mt-5 grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold">{t("stats.raises")}</h3>
              <DivergingBars items={stats.model.likes.map(feature)} />
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold">{t("stats.lowers")}</h3>
              <DivergingBars items={stats.model.dislikes.map(feature)} />
            </div>
          </div>
          <p className="mt-4 text-xs text-muted">
            {t("stats.thresholds", {
              a: thresholds[0] ?? "–",
              b: thresholds[1] ?? "–",
              c: thresholds[2] ?? "–",
              d: thresholds[3] ?? "–",
            })}
          </p>
        </Card>
      ) : (
        <Card title={t("stats.model")}>
          <p className="text-sm text-muted">{t("stats.noModel")}</p>
        </Card>
      )}

      {stats.plan_to_watch.length > 0 && (
        <Card
          title={t("stats.plan")}
          subtitle={stats.model ? t("stats.byPrediction") : t("stats.byMal")}
        >
          <ol className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {stats.plan_to_watch.map((show, i) => (
              <li key={show.id}>
                <ShowRow show={show} rank={i + 1} />
              </li>
            ))}
          </ol>
        </Card>
      )}
    </div>
  );
}

function Card({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-lg bg-surface-raised p-5">
      <h2 className="text-lg font-bold">{title}</h2>
      {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="rounded-lg bg-surface-raised p-4">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-black md:text-3xl">{value}</div>
      {note && <div className="mt-0.5 text-xs text-neutral-400">{note}</div>}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function StatusBars({ stats }: { stats: Stats }) {
  const { t } = useT();
  const max = Math.max(1, ...stats.overview.by_status.map((s) => s.count));
  return (
    <ul className="space-y-2 text-sm">
      {stats.overview.by_status.map((s) => (
        <li key={s.status} className="grid grid-cols-[7rem_1fr_3rem] items-center gap-3">
          <span className="text-neutral-200">{t(`list.${s.status}`)}</span>
          <span className="h-3">
            <span
              className="block h-full rounded-r"
              style={{ width: `${(s.count / max) * 100}%`, background: YOU }}
            />
          </span>
          <span className="text-right tabular-nums">{s.count}</span>
        </li>
      ))}
    </ul>
  );
}

function TagBars({ items, empty }: { items: TagStat[]; empty: string }) {
  const { t, lang } = useT();
  const { num } = numbers(lang);
  if (!items.length) return <p className="text-sm text-muted">{empty}</p>;
  const name = (s: TagStat) => featureName(lang, s.key, s.name);
  return (
    <>
      <DivergingBars
        items={items.map((s) => ({
          name: name(s),
          value: s.affinity ?? 0,
          detail:
            t("stats.tagDetail", {
              kind: kindOne(t, s.kind),
              count: s.count,
              mine: num(s.mean_score),
              mal: num(s.mal_mean),
            }) + (s.dropped ? t("stats.tagDropped", { count: s.dropped }) : ""),
        }))}
      />
      <p className="mt-3 text-xs text-muted">
        {items
          .slice(0, 3)
          .map((s) =>
            t("stats.tagSummary", {
              name: name(s),
              count: s.count,
              mine: num(s.mean_score, 1),
              mal: num(s.mal_mean, 1),
            }),
          )
          .join(" · ")}
      </p>
    </>
  );
}

/** A hot take's title and text, worded from its kind and numbers. */
function hotTakeText(t: T, lang: Lang, take: HotTake): { title: string; text: string } {
  const p = take.params;
  const text = (key: string, vars: object) => (t as (k: string, v: object) => string)(key, vars);
  switch (take.kind) {
    case "agreement":
      return {
        title: t(`take.agreement.${p.level as "own"}`),
        text: text("take.agreement.text", p),
      };
    case "tag_contrarian": {
      const vars = { ...p, name: featureName(lang, String(p.key), String(p.name)) };
      return {
        title: text("take.tag_contrarian.title", vars),
        text: text("take.tag_contrarian.text", vars),
      };
    }
    default:
      return { title: text(`take.${take.kind}.title`, p), text: text(`take.${take.kind}.text`, p) };
  }
}

const KNOWN_TAKES = new Set([
  "harsh",
  "generous",
  "agreement",
  "underrated",
  "overrated",
  "dropped_acclaimed",
  "hidden_gem",
  "tag_contrarian",
]);

function HotTakeCard({ take }: { take: HotTake }) {
  const { t, lang } = useT();
  if (!KNOWN_TAKES.has(take.kind)) return null;
  const { title, text } = hotTakeText(t, lang, take);
  const body = (
    <div className="flex h-full gap-3 rounded-lg bg-surface-raised p-4 transition-colors hover:bg-white/10">
      {allowedImage(take.anime?.picture_url) && (
        <Image
          src={allowedImage(take.anime?.picture_url)!}
          alt=""
          width={56}
          height={80}
          className="h-20 w-14 shrink-0 rounded object-cover"
        />
      )}
      <div className="min-w-0">
        <div className="text-xs font-semibold tracking-wide text-brand uppercase">{title}</div>
        {take.anime && (
          <div className="mt-0.5 truncate font-semibold">{displayTitle(take.anime)}</div>
        )}
        <p className="mt-1 text-sm text-neutral-300">{text}</p>
      </div>
    </div>
  );
  return take.anime ? <Link href={`/anime/${take.anime.id}`}>{body}</Link> : body;
}

function ShowRow({ show, rank }: { show: ShowRef; rank: number }) {
  const { lang } = useT();
  return (
    <Link
      href={`/anime/${show.id}`}
      className="flex items-center gap-3 rounded p-1 hover:bg-white/5"
    >
      <span className="w-5 text-right text-sm text-muted tabular-nums">{rank}</span>
      {allowedImage(show.picture_url) ? (
        <Image
          src={allowedImage(show.picture_url)!}
          alt=""
          width={40}
          height={56}
          className="h-14 w-10 shrink-0 rounded object-cover"
        />
      ) : (
        <span className="h-14 w-10 shrink-0 rounded bg-white/5" />
      )}
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold">{displayTitle(show)}</span>
        <span className="mt-1 flex items-center gap-2 text-xs text-muted">
          <PredictionBadge prediction={show.prediction} force />
          {show.mean !== null && <span>MAL {formatNumber(lang, show.mean, 2)}</span>}
        </span>
      </span>
    </Link>
  );
}
