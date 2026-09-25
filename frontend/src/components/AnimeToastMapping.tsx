"use client";

import { useEffect, useState } from "react";
import type { ProviderMapping } from "@/lib/types";
import { SCAN_FINISHED_EVENT, SOURCES_CHANGED_EVENT } from "./EpisodeBrowser";
import { useT } from "./I18nProvider";

/** Which animetoast pages (one per language) feed this show, with a manual correction. */
export function AnimeToastMapping({ animeId }: { animeId: number }) {
  const { t } = useT();
  const [enabled, setEnabled] = useState(false);
  const [mapping, setMapping] = useState<ProviderMapping | null | undefined>(undefined);
  const [slugs, setSlugs] = useState("");
  const [offset, setOffset] = useState(0);
  const [message, setMessage] = useState<string | null>(null);

  function apply(found: ProviderMapping | null) {
    setMapping(found);
    setSlugs(found?.external_id?.split(",").join(", ") ?? "");
    setOffset(found?.episode_offset ?? 0);
  }

  useEffect(() => {
    fetch("/api/providers")
      .then((res) => (res.ok ? res.json() : []))
      .then((names: string[]) => setEnabled(names.includes("animetoast")))
      .catch(() => setEnabled(false));
    const load = () =>
      fetch(`/api/anime/${animeId}/mappings`)
        .then((res) => (res.ok ? res.json() : []))
        .then((all: ProviderMapping[]) =>
          apply(all.find((m) => m.provider === "animetoast") ?? null),
        )
        .catch(() => apply(null));
    load();
    window.addEventListener(SCAN_FINISHED_EVENT, load);
    return () => window.removeEventListener(SCAN_FINISHED_EVENT, load);
  }, [animeId]);

  const parsed = slugs
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  async function save() {
    const res = await fetch(`/api/anime/${animeId}/mappings/animetoast`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ slugs: parsed, episode_offset: offset }),
    });
    if (res.ok) {
      apply({
        provider: "animetoast",
        external_id: parsed.join(","),
        season: null,
        episode_offset: offset,
        manual: true,
      });
      setMessage(t("mapping.savedToast"));
      window.dispatchEvent(new Event(SOURCES_CHANGED_EVENT));
    } else {
      setMessage(res.status === 422 ? t("mapping.slugHintToast") : t("mapping.saveFailed"));
    }
  }

  async function reset() {
    await fetch(`/api/anime/${animeId}/mappings/animetoast`, { method: "DELETE" });
    apply(null);
    setMessage(t("mapping.resetToast"));
    window.dispatchEvent(new Event(SOURCES_CHANGED_EVENT));
  }

  if (!enabled || mapping === undefined) return null;

  const status = mapping?.external_id
    ? `${mapping.manual ? t("mapping.manual") : t("mapping.detected")}: ${mapping.external_id.split(",").join(", ")}${mapping.episode_offset ? `, ${t("mapping.offset", { offset: mapping.episode_offset })}` : ""}`
    : mapping
      ? t("mapping.notFound", { site: "animetoast" })
      : t("mapping.notDetected");

  return (
    <section className="mt-6 max-w-2xl rounded-lg bg-surface-raised p-6">
      <h2 className="text-lg font-semibold">{t("mapping.toastTitle")}</h2>
      <p className="mt-1 text-sm text-muted">{status}</p>
      <p className="mt-1 text-xs text-muted">{t("mapping.toastInfo")}</p>
      <div className="mt-4 flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          {t("mapping.pageSlugs")}
          <input
            value={slugs}
            onChange={(e) => setSlugs(e.target.value)}
            placeholder="naruto-ger-dub, naruto-ger-sub"
            className="w-80 rounded bg-neutral-800 px-2 py-1"
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
          disabled={parsed.length === 0}
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
