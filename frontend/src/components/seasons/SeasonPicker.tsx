"use client";

import { useRouter } from "next/navigation";
import { SEASONS, currentSeason, seasonHref } from "@/lib/seasons";
import type { SeasonName } from "@/lib/types";
import { useT } from "../I18nProvider";

const FIRST_YEAR = 1960;

/** Jump to any season: a year and one of its four seasons. */
export function SeasonPicker({ year, season }: { year: number; season: SeasonName }) {
  const { t } = useT();
  const router = useRouter();
  const last = currentSeason().year + 1;
  const years = Array.from({ length: last - FIRST_YEAR + 1 }, (_, i) => last - i);
  const select = "rounded border border-white/20 bg-surface-raised px-3 py-1.5 text-sm";
  return (
    <div className="ml-auto flex gap-2">
      <select
        aria-label={t("seasons.season")}
        value={season}
        onChange={(e) => router.push(seasonHref({ year, season: e.target.value as SeasonName }))}
        className={select}
      >
        {SEASONS.map((s) => (
          <option key={s} value={s}>
            {t(`seasons.name.${s}`)}
          </option>
        ))}
      </select>
      <select
        aria-label={t("seasons.year")}
        value={year}
        onChange={(e) => router.push(seasonHref({ year: Number(e.target.value), season }))}
        className={select}
      >
        {years.map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>
    </div>
  );
}
