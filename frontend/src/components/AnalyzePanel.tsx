"use client";

import { useEffect, useState } from "react";
import { LanguageFlag } from "@/components/LanguageFlag";
import { LANGUAGE_LABELS } from "@/lib/languages";
import type { AnalysisJob, Availability, Language } from "@/lib/types";
import { SCAN_FINISHED_EVENT } from "./EpisodeBrowser";
import { useStoredValue } from "./player/useStoredValue";

const POLL_MS = 3000;

/**
 * Two episodes by default. Episode 1 often has no opening (or a different cut of it), so the
 * 2nd and 3rd are used when they exist, the 1st only when there aren't enough.
 */
function defaultRange(available: number[]): [number, number] | null {
  if (available.length < 2) return null;
  return available.length >= 3 ? [available[1], available[2]] : [available[0], available[1]];
}

async function fetchAvailability(animeId: number): Promise<Availability | null> {
  try {
    const res = await fetch(`/api/anime/${animeId}/availability`);
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  }
}

export function AnalyzePanel({ animeId, signedIn }: { animeId: number; signedIn: boolean }) {
  // The language picked for the episode list; only its direct streams are analysed.
  const [language] = useStoredValue<Language>("notflix:language", "de-dub");
  const [availability, setAvailability] = useState<Availability | null>(null);
  const [custom, setCustom] = useState<{ language: Language; from: number; to: number } | null>(
    null,
  );
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const running = job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    const load = () => fetchAvailability(animeId).then((found) => found && setAvailability(found));
    load();
    window.addEventListener(SCAN_FINISHED_EVENT, load);
    return () => window.removeEventListener(SCAN_FINISHED_EVENT, load);
  }, [animeId]);

  // Keep up while the providers are still being scanned.
  const scanning = availability?.scanning ?? false;
  useEffect(() => {
    if (!scanning) return;
    const timer = setInterval(
      () => fetchAvailability(animeId).then((found) => found && setAvailability(found)),
      POLL_MS,
    );
    return () => clearInterval(timer);
  }, [animeId, scanning]);

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      const res = await fetch(`/api/analysis/jobs/${job.id}`);
      if (res.ok) setJob(await res.json());
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [running, job?.id]);

  const available = (availability?.episodes ?? [])
    .filter((e) => e.languages.includes(language))
    .map((e) => e.episode)
    .sort((a, b) => a - b);
  const fallback = defaultRange(available);
  // A range picked for another language doesn't carry over.
  const [from, to] =
    custom?.language === language ? [custom.from, custom.to] : (fallback ?? [1, 2]);
  const episodes = available.filter((ep) => ep >= from && ep <= to);
  const label = LANGUAGE_LABELS[language];

  async function analyze() {
    setMessage(null);
    const res = await fetch(`/api/anime/${animeId}/analyze`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ episodes, language }),
    });
    if (!res.ok) {
      setMessage(`Could not start analysis (${res.status})`);
      return;
    }
    const body: { cached: boolean; job: AnalysisJob | null } = await res.json();
    if (body.cached) setMessage("These episodes are already analysed.");
    setJob(body.job);
  }

  if (!signedIn) return null;

  let hint: string;
  if (!availability || (availability.scanning && !fallback)) {
    hint = "Checking which episodes are available…";
  } else if (!fallback) {
    hint = `Needs at least two episodes in ${label}; ${available.length === 1 ? "only one was" : "none were"} found. Pick another language in the episode list.`;
  } else if (episodes.length < 2) {
    hint = `Pick a range with at least two ${label} episodes.`;
  } else {
    hint = `Analyses episode${episodes.length > 1 ? "s" : ""} ${episodes.join(", ")} using their direct ${label} streams.`;
  }

  const setRange = (next: { from?: number; to?: number }) =>
    setCustom({ language, from, to, ...next });

  return (
    <section className="mt-6 max-w-2xl rounded-lg bg-surface-raised p-6">
      <h2 className="text-lg font-semibold">Intro &amp; outro detection</h2>
      <p className="mt-1 text-sm text-muted">
        Compares the audio of neighbouring episodes to find the shared opening and ending, then
        saves the timestamps for auto-skip. Only local files and direct streams can be analysed, not
        embedded players.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <span className="flex items-center gap-2 rounded bg-neutral-800 px-2 py-1">
          <LanguageFlag language={language} />
          {label}
        </span>
        <label className="flex items-center gap-2">
          Episodes
          <input
            type="number"
            min={available[0] ?? 1}
            max={to - 1}
            value={from}
            disabled={!fallback}
            onChange={(e) => setRange({ from: Number(e.target.value) })}
            className="w-16 rounded bg-neutral-800 px-2 py-1 disabled:opacity-50"
          />
        </label>
        <label className="flex items-center gap-2">
          to
          <input
            type="number"
            min={from + 1}
            max={available.at(-1) ?? 2}
            value={to}
            disabled={!fallback}
            onChange={(e) => setRange({ to: Number(e.target.value) })}
            className="w-16 rounded bg-neutral-800 px-2 py-1 disabled:opacity-50"
          />
        </label>
        <button
          onClick={analyze}
          disabled={running || episodes.length < 2}
          className="rounded bg-brand px-4 py-1.5 font-semibold hover:bg-brand-dark disabled:opacity-50"
        >
          {running ? "Analysing…" : "Analyse"}
        </button>
      </div>
      <p className="mt-3 text-sm text-muted">{hint}</p>
      {message && <p className="mt-3 text-sm text-muted">{message}</p>}
      {job && (
        <p className="mt-3 text-sm">
          Job for episodes {job.episodes.join(", ")}
          {job.language && ` (${LANGUAGE_LABELS[job.language]})`}:{" "}
          <span className={job.status === "failed" ? "text-red-400" : "text-green-400"}>
            {job.status}
          </span>
          {job.error && <span className="block text-red-400">{job.error}</span>}
        </p>
      )}
    </section>
  );
}
