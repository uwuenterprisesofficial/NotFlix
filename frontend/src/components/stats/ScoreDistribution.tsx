"use client";

import { useT } from "@/components/I18nProvider";
import type { Stats } from "@/lib/types";
import { AXIS, GRID, MAL, YOU } from "./colors";

const HEIGHT = 180;

/** Gridline values from 0 to a round number at or above `max`, about four steps apart. */
function ticks(max: number): number[] {
  const raw = max / 4;
  const step = raw <= 1 ? 1 : raw <= 2 ? 2 : raw <= 5 ? 5 : Math.ceil(raw / 10) * 10;
  const out = [];
  for (let v = 0; v < max + step; v += step) out.push(v);
  return out;
}

/** Your scores next to MAL's (rounded) average for the same shows, per score 1–10. */
export function ScoreDistribution({ data }: { data: Stats["score_distribution"] }) {
  const { t } = useT();
  const max = Math.max(1, ...data.flatMap((d) => [d.mine, d.mal]));
  const top = ticks(max).at(-1)!;
  const h = (v: number) => (v / top) * HEIGHT;

  return (
    <figure>
      <div className="mb-3 flex gap-4 text-xs text-neutral-300" aria-hidden>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: YOU }} />{" "}
          {t("stats.yourScore")}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: MAL }} />{" "}
          {t("stats.malSameShows")}
        </span>
      </div>
      <div className="flex pt-2">
        <div
          className="relative w-8 shrink-0 text-right text-[11px] text-muted tabular-nums"
          style={{ height: HEIGHT }}
        >
          {ticks(max).map((t) => (
            <span key={t} className="absolute right-2 translate-y-1/2" style={{ bottom: h(t) }}>
              {t}
            </span>
          ))}
        </div>
        <div className="relative flex-1">
          <div className="relative" style={{ height: HEIGHT }}>
            {ticks(max).map((t) => (
              <div
                key={t}
                className="absolute inset-x-0 h-px"
                style={{ bottom: h(t), background: t === 0 ? AXIS : GRID }}
              />
            ))}
            <div className="absolute inset-0 flex items-end">
              {data.map((d) => (
                <div
                  key={d.score}
                  tabIndex={0}
                  aria-label={t("stats.scoreAria", { score: d.score, mine: d.mine, mal: d.mal })}
                  className="group relative flex h-full flex-1 items-end justify-center gap-0.5 outline-none hover:bg-white/5 focus-visible:bg-white/10"
                >
                  <div
                    className="w-[40%] max-w-6 rounded-t"
                    style={{ height: h(d.mine), background: YOU }}
                  />
                  <div
                    className="w-[40%] max-w-6 rounded-t"
                    style={{ height: h(d.mal), background: MAL }}
                  />
                  <div className="pointer-events-none absolute bottom-full left-1/2 z-10 mb-1 hidden -translate-x-1/2 rounded bg-black/90 px-2.5 py-1.5 text-xs whitespace-nowrap shadow-lg group-hover:block group-focus-visible:block">
                    <div className="text-muted">{t("stats.scoreN", { score: d.score })}</div>
                    <div className="flex items-center gap-1.5">
                      <span className="h-0.5 w-3" style={{ background: YOU }} />
                      <strong>{d.mine}</strong> <span className="text-muted">{t("stats.you")}</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="h-0.5 w-3" style={{ background: MAL }} />
                      <strong>{d.mal}</strong> <span className="text-muted">{t("stats.mal")}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="flex text-[11px] text-muted">
            {data.map((d) => (
              <span key={d.score} className="flex-1 pt-1 text-center tabular-nums">
                {d.score}
              </span>
            ))}
          </div>
        </div>
      </div>
      <details className="mt-3 text-xs text-muted">
        <summary className="cursor-pointer">{t("stats.asTable")}</summary>
        <table className="mt-2 w-full max-w-sm tabular-nums">
          <thead>
            <tr className="text-left">
              <th className="font-normal">{t("stats.score")}</th>
              <th className="font-normal">{t("stats.you")}</th>
              <th className="font-normal">{t("stats.mal")}</th>
            </tr>
          </thead>
          <tbody className="text-neutral-200">
            {data.map((d) => (
              <tr key={d.score}>
                <td>{d.score}</td>
                <td>{d.mine}</td>
                <td>{d.mal}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
