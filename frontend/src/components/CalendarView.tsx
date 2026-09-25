"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { displayTitle, relativeTime } from "@/lib/format";
import { LOCALE } from "@/lib/i18n";
import { allowedImage } from "@/lib/images";
import type { AnimeCard, CalendarResponse } from "@/lib/types";
import { useNow } from "@/lib/useNow";
import { useT } from "./I18nProvider";
import { PredictionBadge } from "./PredictionBadge";

const DAY_MS = 86_400_000;
const REFRESH_POLL_MS = 3000;

/** Monday 00:00 (local time) of the week `offset` weeks from this one. */
function weekStart(offset: number): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + offset * 7);
  return d;
}

function dayKey(d: Date): string {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

/** A week of episodes, one column per local day. */
export function CalendarView() {
  const { t, lang } = useT();
  const now = useNow();
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ offset: number; items: AnimeCard[] } | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [failed, setFailed] = useState(false);
  const [mine, setMine] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const start = weekStart(offset);
    const end = new Date(start.getTime() + 7 * DAY_MS);
    const load = async () => {
      try {
        const res = await fetch(
          `/api/calendar?${new URLSearchParams({ start: start.toISOString(), end: end.toISOString() })}`,
        );
        if (!res.ok) throw new Error(String(res.status));
        const body: CalendarResponse = await res.json();
        if (cancelled) return;
        setData({ offset, items: body.items });
        setFailed(false);
        setRefreshing(body.refreshing);
        if (body.refreshing) timer = setTimeout(load, REFRESH_POLL_MS);
      } catch {
        if (!cancelled) setFailed(true);
      }
    };
    load();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [offset]);

  const start = weekStart(offset);
  const days = Array.from({ length: 7 }, (_, i) => new Date(start.getTime() + i * DAY_MS));
  const items = (data?.offset === offset ? data.items : []).filter(
    (a) => !mine || (a.progress && a.progress.status !== "dropped"),
  );
  const byDay = new Map<string, AnimeCard[]>();
  for (const a of items) {
    const key = dayKey(new Date(a.airing!.airing_at));
    byDay.set(key, [...(byDay.get(key) ?? []), a]);
  }
  const today = dayKey(new Date());
  const loading = data?.offset !== offset && !failed;

  return (
    <div className="mt-6">
      <div className="mb-4 flex flex-wrap items-center gap-3 text-sm">
        <button
          onClick={() => setOffset(offset - 1)}
          className="rounded bg-surface-raised px-3 py-1.5 hover:bg-neutral-700"
        >
          {t("calendar.prev")}
        </button>
        <button
          onClick={() => setOffset(0)}
          disabled={offset === 0}
          className="rounded bg-surface-raised px-3 py-1.5 hover:bg-neutral-700 disabled:opacity-50"
        >
          {t("calendar.thisWeek")}
        </button>
        <button
          onClick={() => setOffset(offset + 1)}
          className="rounded bg-surface-raised px-3 py-1.5 hover:bg-neutral-700"
        >
          {t("calendar.next")}
        </button>
        <label className="ml-auto flex items-center gap-2">
          <input
            type="checkbox"
            checked={mine}
            onChange={(e) => setMine(e.target.checked)}
            className="accent-brand"
          />
          {t("calendar.mine")}
        </label>
      </div>
      <p className="mb-3 min-h-5 text-sm text-muted" aria-live="polite">
        {failed
          ? t("calendar.failed")
          : loading
            ? t("calendar.loading")
            : refreshing
              ? t("calendar.updating")
              : ""}
      </p>

      <div className="grid gap-3 md:grid-cols-7">
        {days.map((day) => {
          const key = dayKey(day);
          const entries = byDay.get(key) ?? [];
          const isToday = key === today;
          return (
            <section
              key={key}
              className={`rounded-lg p-2 ${isToday ? "bg-surface-raised ring-1 ring-brand" : "bg-surface-raised/60"}`}
            >
              <h2 className="mb-2 px-1 text-sm font-semibold">
                {day.toLocaleDateString(LOCALE[lang], { weekday: "long" })}
                <span className="ml-1.5 font-normal text-muted">
                  {isToday
                    ? t("calendar.today")
                    : day.toLocaleDateString(LOCALE[lang], { day: "numeric", month: "short" })}
                </span>
              </h2>
              {entries.length === 0 && !loading && (
                <p className="px-1 text-xs text-muted">{t("calendar.empty")}</p>
              )}
              <ul className="space-y-1.5">
                {entries.map((a) => (
                  <li key={`${a.id}-${a.airing!.episode}`}>
                    <Entry anime={a} now={now} />
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function Entry({ anime, now }: { anime: AnimeCard; now: number | null }) {
  const { t, lang } = useT();
  const airing = anime.airing!;
  const at = new Date(airing.airing_at);
  const aired = now !== null && at.getTime() <= now;
  const picture = allowedImage(anime.picture_url);
  const onList = anime.progress && anime.progress.status !== "dropped";
  return (
    <Link
      href={aired ? `/watch/${anime.id}/${airing.episode}` : `/anime/${anime.id}`}
      className={`flex gap-2 rounded p-1.5 hover:bg-white/10 ${aired ? "" : "opacity-80"} ${onList ? "bg-white/5" : ""}`}
    >
      {picture ? (
        <Image
          src={picture}
          alt=""
          width={36}
          height={52}
          className="h-13 w-9 shrink-0 rounded object-cover"
        />
      ) : (
        <span className="h-13 w-9 shrink-0 rounded bg-white/5" />
      )}
      <span className="min-w-0 text-xs">
        <span className="block font-semibold tabular-nums">
          {at.toLocaleTimeString(LOCALE[lang], { hour: "2-digit", minute: "2-digit" })}
          {now !== null && (
            <span className="ml-1 font-normal text-muted">
              {aired ? `· ${t("calendar.aired")}` : `· ${relativeTime(lang, at, now)}`}
            </span>
          )}
        </span>
        <span className="line-clamp-2 text-sm leading-tight" title={displayTitle(anime)}>
          {displayTitle(anime)}
        </span>
        <span className="mt-0.5 flex items-center gap-1.5 text-muted">
          {t("airing.episode", { episode: airing.episode })}
          {onList && <span className="text-brand">●</span>}
          <PredictionBadge prediction={anime.prediction} />
        </span>
      </span>
    </Link>
  );
}
