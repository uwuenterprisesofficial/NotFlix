"use client";

import { useEffect, useState } from "react";
import type { ProviderMapping } from "@/lib/types";
import { SCAN_FINISHED_EVENT, SOURCES_CHANGED_EVENT } from "./EpisodeBrowser";
import { useT } from "./I18nProvider";

/** Shows which AniWorld series/season feeds the German sources and lets the user correct it. */
export function AniWorldMapping({ animeId }: { animeId: number }) {
  const { t } = useT();
  const [mapping, setMapping] = useState<ProviderMapping | null | undefined>(undefined);
  const [slug, setSlug] = useState("");
  const [season, setSeason] = useState(1);
  const [offset, setOffset] = useState(0);
  const [message, setMessage] = useState<string | null>(null);

  function apply(found: ProviderMapping | null) {
    setMapping(found);
    setSlug(found?.external_id ?? "");
    setSeason(found?.season ?? 1);
    setOffset(found?.episode_offset ?? 0);
  }

  useEffect(() => {
    const load = () =>
      fetch(`/api/anime/${animeId}/mappings`)
        .then((res) => (res.ok ? res.json() : []))
        .then((all: ProviderMapping[]) => apply(all.find((m) => m.provider === "aniworld") ?? null))
        .catch(() => apply(null));
    load();
    window.addEventListener(SCAN_FINISHED_EVENT, load);
    return () => window.removeEventListener(SCAN_FINISHED_EVENT, load);
  }, [animeId]);

  async function save() {
    const res = await fetch(`/api/anime/${animeId}/mappings/aniworld`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ slug: slug.trim(), season, episode_offset: offset }),
    });
    if (res.ok) {
      apply({
        provider: "aniworld",
        external_id: slug.trim(),
        season,
        episode_offset: offset,
        manual: true,
      });
      setMessage(t("mapping.saved"));
      window.dispatchEvent(new Event(SOURCES_CHANGED_EVENT));
    } else {
      setMessage(res.status === 422 ? t("mapping.slugHint") : t("mapping.saveFailed"));
    }
  }

  async function reset() {
    await fetch(`/api/anime/${animeId}/mappings/aniworld`, { method: "DELETE" });
    apply(null);
    setMessage(t("mapping.reset"));
    window.dispatchEvent(new Event(SOURCES_CHANGED_EVENT));
  }

  if (mapping === undefined) return null;

  const status = mapping?.external_id
    ? `${mapping.manual ? t("mapping.manual") : t("mapping.detected")}: ${mapping.external_id}, ${t("mapping.season", { season: mapping.season ?? 1 })}${mapping.episode_offset ? `, ${t("mapping.offset", { offset: mapping.episode_offset })}` : ""}`
    : mapping
      ? t("mapping.notFound", { site: "AniWorld" })
      : t("mapping.notDetected");

  return (
    <section className="mt-6 max-w-2xl rounded-lg bg-surface-raised p-6">
      <h2 className="text-lg font-semibold">{t("mapping.aniworldTitle")}</h2>
      <p className="mt-1 text-sm text-muted">{status}</p>
      <div className="mt-4 flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          {t("mapping.seriesSlug")}
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="one-piece"
            className="w-56 rounded bg-neutral-800 px-2 py-1"
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("mapping.seasonLabel")}
          <input
            type="number"
            min={0}
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
            className="w-20 rounded bg-neutral-800 px-2 py-1"
          />
        </label>
        <label className="flex flex-col gap-1" title={t("mapping.offsetInfo")}>
          {t("mapping.offsetLabel")}
          <input
            type="number"
            value={offset}
            onChange={(e) => setOffset(Number(e.target.value))}
            className="w-20 rounded bg-neutral-800 px-2 py-1"
          />
        </label>
        <button
          onClick={save}
          disabled={!slug.trim()}
          className="rounded bg-brand px-4 py-1.5 font-semibold hover:bg-brand-dark disabled:opacity-50"
        >
          {t("mapping.save")}
        </button>
        {mapping && (
          <button onClick={reset} className="rounded px-3 py-1.5 text-muted hover:text-white">
            {t("mapping.resetButton")}
          </button>
        )}
      </div>
      {message && <p className="mt-3 text-sm text-muted">{message}</p>}
    </section>
  );
}
