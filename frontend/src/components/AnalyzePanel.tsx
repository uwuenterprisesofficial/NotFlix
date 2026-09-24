"use client";

import { useEffect, useState } from "react";
import type { AnalysisJob } from "@/lib/types";

const POLL_MS = 3000;

export function AnalyzePanel({
  animeId,
  episodeCount,
  signedIn,
}: {
  animeId: number;
  episodeCount: number;
  signedIn: boolean;
}) {
  const [from, setFrom] = useState(1);
  const [to, setTo] = useState(Math.min(episodeCount, 3));
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const running = job?.status === "queued" || job?.status === "running";

  useEffect(() => {
    if (!running) return;
    const timer = setInterval(async () => {
      const res = await fetch(`/api/analysis/jobs/${job.id}`);
      if (res.ok) setJob(await res.json());
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [running, job?.id]);

  async function analyze() {
    setMessage(null);
    const episodes = Array.from({ length: to - from + 1 }, (_, i) => from + i);
    const res = await fetch(`/api/anime/${animeId}/analyze`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ episodes }),
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

  return (
    <section className="mt-12 max-w-2xl rounded-lg bg-surface-raised p-6">
      <h2 className="text-lg font-semibold">Intro &amp; outro detection</h2>
      <p className="mt-1 text-sm text-muted">
        Compares the audio of neighbouring episodes to find the shared opening and ending, then
        saves the timestamps for auto-skip. Needs a local file or a direct stream for each episode.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2">
          Episodes
          <input
            type="number"
            min={1}
            max={to - 1}
            value={from}
            onChange={(e) => setFrom(Number(e.target.value))}
            className="w-16 rounded bg-neutral-800 px-2 py-1"
          />
        </label>
        <label className="flex items-center gap-2">
          to
          <input
            type="number"
            min={from + 1}
            max={episodeCount}
            value={to}
            onChange={(e) => setTo(Number(e.target.value))}
            className="w-16 rounded bg-neutral-800 px-2 py-1"
          />
        </label>
        <button
          onClick={analyze}
          disabled={running || to <= from}
          className="rounded bg-brand px-4 py-1.5 font-semibold hover:bg-brand-dark disabled:opacity-50"
        >
          {running ? "Analysing…" : "Analyse"}
        </button>
      </div>
      {message && <p className="mt-3 text-sm text-muted">{message}</p>}
      {job && (
        <p className="mt-3 text-sm">
          Job for episodes {job.episodes.join(", ")}:{" "}
          <span className={job.status === "failed" ? "text-red-400" : "text-green-400"}>
            {job.status}
          </span>
          {job.error && <span className="block text-red-400">{job.error}</span>}
        </p>
      )}
    </section>
  );
}
