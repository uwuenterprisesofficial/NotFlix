"use client";

import { useEffect, useState } from "react";
import type { ProviderMapping } from "@/lib/types";
import { SCAN_FINISHED_EVENT, SOURCES_CHANGED_EVENT } from "./EpisodeBrowser";

/** Shows which AniWorld series/season feeds the German sources and lets the user correct it. */
export function AniWorldMapping({ animeId }: { animeId: number }) {
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
      setMessage("Saved. Looking for German sources with this mapping…");
      window.dispatchEvent(new Event(SOURCES_CHANGED_EVENT));
    } else {
      setMessage(
        res.status === 422
          ? "Use the slug from the AniWorld URL, e.g. one-piece."
          : "Saving failed.",
      );
    }
  }

  async function reset() {
    await fetch(`/api/anime/${animeId}/mappings/aniworld`, { method: "DELETE" });
    apply(null);
    setMessage("Reset. Detecting the series again…");
    window.dispatchEvent(new Event(SOURCES_CHANGED_EVENT));
  }

  if (mapping === undefined) return null;

  const status = mapping?.external_id
    ? `${mapping.manual ? "Set manually" : "Detected"}: ${mapping.external_id}, season ${mapping.season}${mapping.episode_offset ? `, episode offset ${mapping.episode_offset}` : ""}`
    : mapping
      ? "Not found on AniWorld automatically."
      : "Not detected yet. It is looked up while the episode list loads.";

  return (
    <section className="mt-6 max-w-2xl rounded-lg bg-surface-raised p-6">
      <h2 className="text-lg font-semibold">German sources (AniWorld)</h2>
      <p className="mt-1 text-sm text-muted">{status}</p>
      <div className="mt-4 flex flex-wrap items-end gap-3 text-sm">
        <label className="flex flex-col gap-1">
          Series slug
          <input
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="one-piece"
            className="w-56 rounded bg-neutral-800 px-2 py-1"
          />
        </label>
        <label className="flex flex-col gap-1">
          Season
          <input
            type="number"
            min={0}
            value={season}
            onChange={(e) => setSeason(Number(e.target.value))}
            className="w-20 rounded bg-neutral-800 px-2 py-1"
          />
        </label>
        <label
          className="flex flex-col gap-1"
          title="Added to the episode number, for shows AniWorld numbers continuously"
        >
          Episode offset
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
          Save
        </button>
        {mapping && (
          <button onClick={reset} className="rounded px-3 py-1.5 text-muted hover:text-white">
            Reset
          </button>
        )}
      </div>
      {message && <p className="mt-3 text-sm text-muted">{message}</p>}
    </section>
  );
}
