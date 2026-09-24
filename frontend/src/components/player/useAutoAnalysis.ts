import { useEffect, useRef, useState } from "react";
import type { AnalysisJob, Episode, Language, SkipSegment } from "@/lib/types";

const POLL_MS = 5000;

/**
 * Intro/outro detection while watching: once a direct stream plays, the backend is asked to
 * analyse this episode and the next one if they have no times yet (it skips what's done). When
 * the job finishes, this episode's new times are returned so Skip Intro etc. can use them.
 */
export function useAutoAnalysis(animeId: number, episode: number, enabled: boolean) {
  const requested = useRef(false);
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [segments, setSegments] = useState<SkipSegment[] | null>(null);

  function start(language: Language) {
    if (!enabled || requested.current) return;
    requested.current = true;
    fetch(`/api/anime/${animeId}/analyze/auto`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ episode, language }),
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((body: { job: AnalysisJob | null } | null) => body?.job && setJob(body.job))
      .catch(() => {});
  }

  const jobId = job?.id;
  const waiting = job?.status === "queued" || job?.status === "running";
  const coversEpisode = !!job?.episodes.includes(episode);
  useEffect(() => {
    if (!jobId || !waiting) return;
    const timer = setInterval(async () => {
      const res = await fetch(`/api/analysis/jobs/${jobId}`).catch(() => null);
      if (res?.ok) setJob(await res.json());
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [jobId, waiting]);

  const finished = job?.status === "done";
  useEffect(() => {
    if (!finished || !coversEpisode) return;
    fetch(`/api/anime/${animeId}/episodes/${episode}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data: Episode | null) => data?.skip_segments.length && setSegments(data.skip_segments))
      .catch(() => {});
  }, [finished, coversEpisode, animeId, episode]);

  return { start, job, segments, detecting: waiting && coversEpisode };
}
