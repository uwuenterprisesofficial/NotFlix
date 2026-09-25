"use client";

import { useEffect, useState } from "react";
import { LanguageFlag } from "@/components/LanguageFlag";
import { formatTime } from "@/lib/format";
import { pickLanguage, useStreamLanguage } from "@/lib/streamLanguage";
import type {
  AnalysisJob,
  AnalysisOverview,
  Availability,
  Language,
  SkipSegment,
} from "@/lib/types";
import { SCAN_FINISHED_EVENT } from "./EpisodeBrowser";
import { useT } from "./I18nProvider";

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
  const { t } = useT();
  // The episode list's language (see streamLanguage); only its direct streams are analysed.
  const { order, chosen } = useStreamLanguage(animeId);
  const [availability, setAvailability] = useState<Availability | null>(null);
  const [custom, setCustom] = useState<{ language: Language; from: number; to: number } | null>(
    null,
  );
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [overview, setOverview] = useState<AnalysisOverview | null>(null);
  const [reload, setReload] = useState(0);
  const [compare, setCompare] = useState(false);

  const running = job?.status === "queued" || job?.status === "running";

  // The saved results; refreshed when a job ends, and polled while any job (e.g. one started
  // while watching) is still waiting or running.
  const jobStatus = job?.status;
  const othersRunning = (overview?.running.length ?? 0) > 0;
  useEffect(() => {
    const load = () =>
      fetch(`/api/anime/${animeId}/analysis`)
        .then((res) => (res.ok ? res.json() : null))
        .then((found: AnalysisOverview | null) => found && setOverview(found))
        .catch(() => {});
    load();
    if (!othersRunning) return;
    const timer = setInterval(load, POLL_MS);
    return () => clearInterval(timer);
  }, [animeId, jobStatus, othersRunning, reload]);

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

  const language = pickLanguage(
    order,
    (availability?.episodes ?? []).flatMap((e) => e.languages),
    chosen,
  );
  const available = (availability?.episodes ?? [])
    .filter((e) => e.languages.includes(language))
    .map((e) => e.episode)
    .sort((a, b) => a - b);
  const fallback = defaultRange(available);
  // A range picked for another language doesn't carry over.
  const [from, to] =
    custom?.language === language ? [custom.from, custom.to] : (fallback ?? [1, 2]);
  const episodes = available.filter((ep) => ep >= from && ep <= to);
  const label = t(`lang.${language}`);
  const hasReferences = (overview?.references.length ?? 0) > 0;
  // One episode is enough once there's something to match it against: a saved intro/outro
  // fingerprint, or (to compare) an episode analysed before.
  const minEpisodes =
    (hasReferences && !compare) || overview?.episodes.some((e) => e.analysed) ? 1 : 2;

  /** Start a manual analysis; it replaces these episodes' earlier results. */
  async function submit(eps: number[], options: { redownload?: boolean } = {}) {
    setMessage(null);
    const res = await fetch(`/api/anime/${animeId}/analyze`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ episodes: eps, language, compare, ...options }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      const detail = typeof body?.detail === "string" ? body.detail : null;
      setMessage(detail ?? t("analysis.startFailed", { status: res.status }));
      return;
    }
    const body: { job: AnalysisJob | null } = await res.json();
    setJob(body.job);
    setReload((r) => r + 1);
  }

  async function stop(jobId: string) {
    const res = await fetch(`/api/analysis/jobs/${jobId}/stop`, { method: "POST" });
    if (res.ok && job?.id === jobId) setJob(await res.json());
    setReload((r) => r + 1);
  }

  async function forget(referenceId: number) {
    await fetch(`/api/anime/${animeId}/analysis/references/${referenceId}`, { method: "DELETE" });
    setReload((r) => r + 1);
  }

  if (!signedIn) return null;

  let hint: string;
  if (!availability || (availability.scanning && !fallback)) {
    hint = t("analysis.checking");
  } else if (!fallback) {
    hint = t("analysis.needsTwo", { label, found: available.length });
  } else if (episodes.length < minEpisodes) {
    hint = t("analysis.pickRange", { label });
  } else {
    hint = t("analysis.hint", { episodes, label, compare });
  }

  const setRange = (next: { from?: number; to?: number }) =>
    setCustom({ language, from, to, ...next });

  return (
    <section className="mt-6 max-w-2xl rounded-lg bg-surface-raised p-6">
      <h2 className="text-lg font-semibold">{t("analysis.title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("analysis.info")}</p>
      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        <span className="flex items-center gap-2 rounded bg-neutral-800 px-2 py-1">
          <LanguageFlag language={language} />
          {label}
        </span>
        <label className="flex items-center gap-2">
          {t("analysis.episodes")}
          <input
            type="number"
            min={available[0] ?? 1}
            max={to - (minEpisodes - 1)}
            value={from}
            disabled={!fallback}
            onChange={(e) => setRange({ from: Number(e.target.value) })}
            className="w-16 rounded bg-neutral-800 px-2 py-1 disabled:opacity-50"
          />
        </label>
        <label className="flex items-center gap-2">
          {t("analysis.to")}
          <input
            type="number"
            min={from + (minEpisodes - 1)}
            max={available.at(-1) ?? 2}
            value={to}
            disabled={!fallback}
            onChange={(e) => setRange({ to: Number(e.target.value) })}
            className="w-16 rounded bg-neutral-800 px-2 py-1 disabled:opacity-50"
          />
        </label>
        <button
          onClick={() => submit(episodes)}
          disabled={running || episodes.length < minEpisodes}
          className="rounded bg-brand px-4 py-1.5 font-semibold hover:bg-brand-dark disabled:opacity-50"
        >
          {running ? t("analysis.analysing") : t("analysis.analyse")}
        </button>
      </div>
      {hasReferences && (
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={compare}
            onChange={(e) => setCompare(e.target.checked)}
            className="accent-brand"
          />
          {t("analysis.compare")}
        </label>
      )}
      <p className="mt-3 text-sm text-muted">{hint}</p>
      {message && <p className="mt-3 text-sm text-muted">{message}</p>}
      {job && (
        <p className="mt-3 text-sm">
          {t("analysis.job", { retry: job.redownload, episodes: job.episodes })}
          {job.language && ` (${t(`lang.${job.language}`)})`}:{" "}
          <span className={job.status === "failed" ? "text-red-400" : "text-green-400"}>
            {t(`jobStatus.${job.status}`)}
          </span>
          {job.error && <span className="block text-red-400">{job.error}</span>}
        </p>
      )}
      {overview && (
        <AnalysisResults
          overview={overview}
          onRetry={(ep) => submit([ep], { redownload: true })}
          onForget={forget}
          onStop={stop}
        />
      )}
    </section>
  );
}

function Range({ label, segment }: { label: string; segment: SkipSegment | undefined }) {
  const { t } = useT();
  if (!segment) return <span className="text-muted">{t("analysis.notFound", { label })}</span>;
  return (
    <span
      title={
        segment.source === "manual"
          ? t("analysis.manual")
          : segment.source === "aniskip"
            ? t("analysis.fromAniSkip")
            : undefined
      }
    >
      {label} {formatTime(segment.start_s)} – {formatTime(segment.end_s)}
    </span>
  );
}

function elapsed(since: string): string {
  return formatTime((Date.now() - Date.parse(since)) / 1000);
}

/** Every analysed episode with its intro and outro times, and what's still being analysed. */
function AnalysisResults({
  overview,
  onRetry,
  onForget,
  onStop,
}: {
  overview: AnalysisOverview;
  onRetry: (episode: number) => void;
  onForget: (referenceId: number) => void;
  onStop: (jobId: string) => void;
}) {
  const { t } = useT();
  const pending = [...new Set(overview.running.flatMap((j) => j.episodes))].sort((a, b) => a - b);
  if (!overview.episodes.length && !pending.length && !overview.references.length) return null;
  return (
    <div className="mt-5 border-t border-white/10 pt-4 text-sm">
      <h3 className="font-semibold">{t("analysis.results")}</h3>
      {overview.references.length > 0 && (
        <div className="mt-1 flex flex-wrap items-center gap-2 text-muted">
          {t("analysis.savedFingerprints")}
          {overview.references.map((r) => (
            <span
              key={r.id}
              className="flex items-center gap-1 rounded bg-neutral-800 py-0.5 pr-1 pl-2 text-white/90"
            >
              {t("analysis.fromEpisode", {
                kind: r.kind === "opening" ? t("player.intro") : t("player.outro"),
                episode: r.source_episode,
                duration: formatTime(r.duration_s),
              })}
              <button
                onClick={() => {
                  if (confirm(t("analysis.confirmRemove"))) onForget(r.id);
                }}
                aria-label={t("analysis.removeLabel", {
                  kind: r.kind === "opening" ? t("player.intro") : t("player.outro"),
                })}
                title={t("analysis.removeTitle")}
                className="rounded px-1 text-muted hover:bg-white/10 hover:text-white"
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}
      {overview.running.map((j) => (
        <p key={j.id} className="mt-1 flex flex-wrap items-center gap-2 text-muted">
          <span>
            {t("analysis.runningJob", { running: j.status === "running", episodes: j.episodes })}
            {j.status === "running" && j.started_at && ` (${elapsed(j.started_at)})`}
          </span>
          <button
            onClick={() => onStop(j.id)}
            aria-label={t("analysis.stopLabel", { episodes: j.episodes })}
            title={t("analysis.stopTitle")}
            className="rounded px-1.5 text-white/80 hover:bg-white/10 hover:text-white"
          >
            ✕
          </button>
        </p>
      ))}
      <ul className="mt-2 max-h-72 space-y-1 overflow-y-auto pr-2">
        {overview.episodes.map((e) => {
          const intro = e.segments.find((s) => s.kind === "opening");
          const outro = e.segments.find((s) => s.kind === "ending");
          const busy = pending.includes(e.episode);
          return (
            <li key={e.episode} className="group flex flex-wrap items-center gap-x-3">
              <span className="w-24 shrink-0 font-semibold">
                {t("analysis.episodeLabel", { episode: e.episode })}
              </span>
              {intro || outro ? (
                <>
                  <Range label={t("player.intro")} segment={intro} />
                  <span aria-hidden className="text-muted">
                    ·
                  </span>
                  <Range label={t("player.outro")} segment={outro} />
                </>
              ) : (
                <span className="text-muted">{t("analysis.nothingFound")}</span>
              )}
              <button
                onClick={() => onRetry(e.episode)}
                disabled={busy}
                title={t("analysis.retryTitle")}
                className="ml-auto rounded px-2 py-0.5 text-xs text-muted hover:bg-white/10 hover:text-white disabled:opacity-50"
              >
                {busy ? t("analysis.analysing") : t("analysis.retry")}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
