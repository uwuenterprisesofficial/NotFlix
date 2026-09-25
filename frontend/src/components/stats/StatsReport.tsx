import Image from "next/image";
import Link from "next/link";
import { PredictionBadge } from "@/components/PredictionBadge";
import { Breakdown } from "@/components/stats/Breakdown";
import { DivergingBars, signed } from "@/components/stats/DivergingBars";
import { ScoreDistribution } from "@/components/stats/ScoreDistribution";
import { YOU } from "@/components/stats/colors";
import { displayTitle } from "@/lib/format";
import type { HotTake, ShowRef, Stats, TagStat } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  watching: "Watching",
  completed: "Completed",
  on_hold: "On hold",
  dropped: "Dropped",
  plan_to_watch: "Plan to watch",
};
const KIND_LABEL: Record<string, string> = {
  genre: "Genre",
  theme: "Theme",
  demographic: "Demographic",
  explicit: "Explicit",
  studio: "Studio",
  source: "Source",
  type: "Type",
  era: "Decade",
};

/** Every section of the statistics page. */
export function StatsReport({ stats }: { stats: Stats }) {
  const o = stats.overview;
  if (o.total === 0) {
    return <p className="text-muted">Press “Sync MAL” to import your list first.</p>;
  }
  return (
    <div className="space-y-10">
      <section className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Shows" value={o.total.toLocaleString("en")} note={`${o.scored} scored`} />
        <Tile
          label="Time watched"
          value={o.days !== null ? `${o.days.toLocaleString("en")} days` : "–"}
          note={`${o.episodes.toLocaleString("en")} episodes`}
        />
        <Tile
          label="Your mean score"
          value={o.mean_score?.toFixed(2) ?? "–"}
          note={
            o.mal_mean !== null ? `MAL: ${o.mal_mean.toFixed(2)} for the same shows` : undefined
          }
        />
        <Tile
          label="Agreement with MAL"
          value={o.agreement !== null ? o.agreement.toFixed(2) : "–"}
          note={
            o.mean_abs_difference !== null
              ? `off by ${o.mean_abs_difference.toFixed(1)} points on average`
              : undefined
          }
        />
      </section>

      <div className="grid gap-6 lg:grid-cols-[3fr_2fr]">
        <Card
          title="Score distribution"
          subtitle="How you score, and how MAL scores the same shows"
        >
          <ScoreDistribution data={stats.score_distribution} />
        </Card>
        <Card
          title="Your list"
          subtitle={
            o.drop_rate !== null
              ? `Drop rate ${(o.drop_rate * 100).toFixed(0)}% of finished shows`
              : undefined
          }
        >
          <StatusBars stats={stats} />
          <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
            <Fact label="Median score" value={o.median_score?.toFixed(1) ?? "–"} />
            <Fact label="Score spread (σ)" value={o.std_score?.toFixed(2) ?? "–"} />
            <Fact
              label="vs MAL on average"
              value={o.mean_difference !== null ? signed(o.mean_difference) : "–"}
            />
            <Fact
              label="Typical show's MAL members"
              value={o.median_members?.toLocaleString("en") ?? "–"}
            />
          </dl>
        </Card>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <Card title="Favourite genres & themes" subtitle="Points above your own average score">
          <TagBars
            items={stats.favourites}
            empty="Score a few more shows to find your favourites."
          />
        </Card>
        <Card
          title="Genres & themes you dislike"
          subtitle="Points below your average (dropped shows count against)"
        >
          <TagBars items={stats.hated} empty="Nothing you consistently dislike — yet." />
        </Card>
      </div>

      {stats.hot_takes.length > 0 && (
        <section>
          <h2 className="text-xl font-bold">Hot takes</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {stats.hot_takes.map((take, i) => (
              <HotTakeCard key={`${take.kind}-${i}`} take={take} />
            ))}
          </div>
        </section>
      )}

      <Card title="Breakdown" subtitle="Everything on your list, by genre, theme, studio and more">
        <Breakdown breakdown={stats.breakdown} />
      </Card>

      {stats.model ? (
        <Card
          title="What predicts your score"
          subtitle={`Learned from your ${stats.model.scored} scored shows; used for the MUST WATCH … AVOID labels`}
        >
          <p className="text-sm text-neutral-300">
            {stats.model.mae !== null && (
              <>
                Predictions for shows the model hadn&apos;t seen were off by{" "}
                <strong>{stats.model.mae.toFixed(2)}</strong> points on average
                {stats.model.baseline_mae !== null && (
                  <> — MAL&apos;s score alone is off by {stats.model.baseline_mae.toFixed(2)}</>
                )}
                .{" "}
              </>
            )}
            Every point of MAL score is worth{" "}
            <strong>{(stats.model.mal_weight ?? 0).toFixed(2)}</strong> of yours.
          </p>
          <div className="mt-5 grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="mb-2 text-sm font-semibold">Raises your score</h3>
              <DivergingBars
                items={stats.model.likes.map((f) => ({
                  name: f.name,
                  value: f.points,
                  detail: KIND_LABEL[f.kind],
                }))}
              />
            </div>
            <div>
              <h3 className="mb-2 text-sm font-semibold">Lowers your score</h3>
              <DivergingBars
                items={stats.model.dislikes.map((f) => ({
                  name: f.name,
                  value: f.points,
                  detail: KIND_LABEL[f.kind],
                }))}
              />
            </div>
          </div>
          <p className="mt-4 text-xs text-muted">
            Label thresholds (predicted score): must watch ≥ {stats.model.thresholds[0]?.toFixed(1)}
            , recommended ≥ {stats.model.thresholds[1]?.toFixed(1)}, maybe ≥{" "}
            {stats.model.thresholds[2]?.toFixed(1)}, probably skip ≥{" "}
            {stats.model.thresholds[3]?.toFixed(1)}, avoid below.
          </p>
        </Card>
      ) : (
        <Card title="What predicts your score">
          <p className="text-sm text-muted">
            Score at least 10 shows on MyAnimeList to get predictions.
          </p>
        </Card>
      )}

      {stats.plan_to_watch.length > 0 && (
        <Card
          title="Your plan to watch, ranked for you"
          subtitle={stats.model ? "By predicted score" : "By MAL score"}
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
  const max = Math.max(1, ...stats.overview.by_status.map((s) => s.count));
  return (
    <ul className="space-y-2 text-sm">
      {stats.overview.by_status.map((s) => (
        <li key={s.status} className="grid grid-cols-[7rem_1fr_3rem] items-center gap-3">
          <span className="text-neutral-200">{STATUS_LABEL[s.status] ?? s.status}</span>
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
  if (!items.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <>
      <DivergingBars
        items={items.map((t) => ({
          name: t.name,
          value: t.affinity ?? 0,
          detail: `${KIND_LABEL[t.kind]} · ${t.count} shows · you ${t.mean_score?.toFixed(2) ?? "–"} · MAL ${t.mal_mean?.toFixed(2) ?? "–"}${t.dropped ? ` · ${t.dropped} dropped` : ""}`,
        }))}
      />
      <p className="mt-3 text-xs text-muted">
        {items
          .slice(0, 3)
          .map(
            (t) =>
              `${t.name}: ${t.count} shows, you ${t.mean_score?.toFixed(1) ?? "–"} vs MAL ${t.mal_mean?.toFixed(1) ?? "–"}`,
          )
          .join(" · ")}
      </p>
    </>
  );
}

function HotTakeCard({ take }: { take: HotTake }) {
  const body = (
    <div className="flex h-full gap-3 rounded-lg bg-surface-raised p-4 transition-colors hover:bg-white/10">
      {take.anime?.picture_url && (
        <Image
          src={take.anime.picture_url}
          alt=""
          width={56}
          height={80}
          className="h-20 w-14 shrink-0 rounded object-cover"
        />
      )}
      <div className="min-w-0">
        <div className="text-xs font-semibold tracking-wide text-brand uppercase">{take.title}</div>
        {take.anime && (
          <div className="mt-0.5 truncate font-semibold">{displayTitle(take.anime)}</div>
        )}
        <p className="mt-1 text-sm text-neutral-300">{take.text}</p>
      </div>
    </div>
  );
  return take.anime ? <Link href={`/anime/${take.anime.id}`}>{body}</Link> : body;
}

function ShowRow({ show, rank }: { show: ShowRef; rank: number }) {
  return (
    <Link
      href={`/anime/${show.id}`}
      className="flex items-center gap-3 rounded p-1 hover:bg-white/5"
    >
      <span className="w-5 text-right text-sm text-muted tabular-nums">{rank}</span>
      {show.picture_url ? (
        <Image
          src={show.picture_url}
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
          {show.mean !== null && <span>MAL {show.mean.toFixed(2)}</span>}
        </span>
      </span>
    </Link>
  );
}
