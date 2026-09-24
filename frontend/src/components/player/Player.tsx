"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { formatTime } from "@/lib/format";
import { LANGUAGE_LABELS } from "@/lib/languages";
import type { Progress, SkipSegment } from "@/lib/types";
import { DirectVideo } from "./DirectVideo";
import { LanguageMenu } from "./LanguageMenu";
import { FullscreenButton, useFrameFullscreen, usePlayerFrame } from "./PlayerFrame";
import { StreamMenu } from "./StreamMenu";
import { useAutoAnalysis } from "./useAutoAnalysis";
import { useAutoSkip } from "./useAutoSkip";
import { useSources } from "./useSources";
import { useStoredValue } from "./useStoredValue";

export function Player({
  animeId,
  episode,
  segments,
  hasNext,
  signedIn,
  watched,
  via,
  server,
}: {
  animeId: number;
  episode: number;
  segments: SkipSegment[];
  hasNext: boolean;
  signedIn: boolean;
  watched: number;
  /** Provider and server the previous episode used; preferred for this one. */
  via: { provider: string | null; label: string | null };
  server: string | null;
}) {
  const router = useRouter();
  const sources = useSources(animeId, episode, { ...via, server });
  const [autoSkip, setAutoSkip] = useAutoSkip();
  const [autoNext, setAutoNext] = useStoredValue<"0" | "1">("notflix:autonext", "1");
  // Episodes watched on MyAnimeList: a count, so unwatching sets it to the episode before.
  const [progress, setProgress] = useState(watched);
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  const savingNow = useRef(false);
  const isWatched = episode <= progress;
  const autoMarked = useRef(false);
  // Where playback is, so a replacement for a stream that broke continues from there.
  const position = useRef(0);
  const { stream } = sources;
  // The video area renders into the layout's frame, which survives moving to the next episode.
  const frame = usePlayerFrame();
  const fullscreen = useFrameFullscreen();

  // The next episode starts with the same provider, source and server when it has them.
  const nextParams = new URLSearchParams();
  if (sources.active) {
    nextParams.set("via", sources.active.provider);
    nextParams.set("option", sources.active.label);
  }
  if (stream) nextParams.set("server", stream.label);
  const nextHref = `/watch/${animeId}/${episode + 1}${nextParams.size ? `?${nextParams}` : ""}`;
  const analysis = useAutoAnalysis(animeId, episode, signedIn);
  // Timestamps from the source itself match its exact cut; analysed ones are the fallback
  // (including ones the analysis started while watching finds).
  const skipSegments = sources.resolved?.skip_segments.length
    ? sources.resolved.skip_segments
    : (analysis.segments ?? segments);

  async function setWatched(value: boolean) {
    if (!signedIn || savingNow.current) return;
    savingNow.current = true;
    setSaving(true);
    setSaveFailed(false);
    const episodes = value ? episode : episode - 1;
    const res = await fetch(`/api/anime/${animeId}/progress`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ episodes_watched: episodes }),
    }).catch(() => null);
    if (res?.ok) {
      const saved: Progress = await res.json();
      setProgress(saved.episodes_watched);
    } else {
      setSaveFailed(true);
    }
    savingNow.current = false;
    setSaving(false);
  }

  function autoMarkWatched() {
    if (autoMarked.current) return;
    autoMarked.current = true;
    if (!isWatched) void setWatched(true);
  }

  return (
    <div>
      {frame &&
        createPortal(
          <>
            {stream?.kind === "direct" && (
              <DirectVideo
                key={stream.url}
                stream={stream}
                segments={skipSegments}
                autoSkip={autoSkip}
                autoNext={autoNext === "1"}
                next={hasNext ? { label: "Next Episode", go: () => router.push(nextHref) } : null}
                onNearEnd={autoMarkWatched}
                onStart={() => {
                  sources.started();
                  // Only direct streams can be analysed; this one is known to play.
                  analysis.start(sources.language);
                }}
                onFail={() => sources.failStream(stream.url)}
                resumeFrom={() => position.current}
                onPosition={(t) => (position.current = t)}
              />
            )}
            {stream?.kind === "embed" && (
              <iframe
                key={stream.url}
                src={stream.url}
                title={`Episode ${episode}`}
                // No sandbox: hosters (VOE, Doodstream, ...) detect it and refuse to play. Browsers
                // already block top-level redirects from cross-origin frames without a user click.
                allow="autoplay; fullscreen; encrypted-media; picture-in-picture"
                allowFullScreen
                onLoad={sources.started}
                className="h-full w-full border-0"
              />
            )}
            {stream?.kind === "embed" && hasNext && (
              // An embedded player's position can't be read, so this can't appear by itself at the
              // credits; it shows while the pointer is over the player instead.
              <Link
                href={nextHref}
                className="absolute top-4 right-4 rounded bg-white/90 px-4 py-2 font-semibold text-black opacity-0 shadow-lg transition-opacity group-hover:opacity-100 focus:opacity-100"
              >
                ▶ Next Episode
              </Link>
            )}
            {stream?.kind === "embed" && (
              <FullscreenButton
                fullscreen={fullscreen}
                className="top-4 left-4 opacity-0 group-hover:opacity-100 focus:opacity-100"
              />
            )}
            {!stream && <PlayerStatus sources={sources} />}
          </>,
          frame,
        )}

      {sources.languages.length > 0 && (
        <div className="mt-4 flex flex-wrap items-start gap-3 text-sm">
          <div className="flex items-center gap-3">
            <LanguageMenu sources={sources} />
            {sources.loading && <span className="text-xs text-muted">Loading more sources…</span>}
          </div>
          <div className="ml-auto">
            <StreamMenu sources={sources} />
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        {stream?.kind === "direct" && (
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={autoSkip}
              onChange={(e) => setAutoSkip(e.target.checked)}
              className="accent-brand"
            />
            Auto-skip intro
          </label>
        )}
        {stream?.kind === "direct" && hasNext && (
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={autoNext === "1"}
              onChange={(e) => setAutoNext(e.target.checked ? "1" : "0")}
              className="accent-brand"
            />
            Autoplay next episode
          </label>
        )}
        <div className="ml-auto flex gap-2">
          {signedIn && (
            <button
              onClick={() => setWatched(!isWatched)}
              disabled={saving}
              aria-pressed={isWatched}
              title={
                !isWatched
                  ? undefined
                  : progress > episode
                    ? `Mark as unwatched: your progress goes back to episode ${episode - 1}`
                    : "Mark as unwatched"
              }
              className="group/watched rounded bg-surface-raised px-3 py-1 hover:bg-neutral-700 disabled:opacity-60"
            >
              {saving ? (
                "Saving…"
              ) : saveFailed ? (
                "Couldn’t save, retry"
              ) : isWatched ? (
                <>
                  <span className="group-hover/watched:hidden">✓ Watched</span>
                  <span className="hidden group-hover/watched:inline">✕ Unwatch</span>
                </>
              ) : (
                "Mark as watched"
              )}
            </button>
          )}
          {hasNext && (
            <Link href={nextHref} className="rounded bg-white px-3 py-1 font-semibold text-black">
              Next episode ›
            </Link>
          )}
        </div>
      </div>

      <SegmentInfo
        segments={skipSegments}
        embedded={stream?.kind === "embed"}
        detecting={analysis.detecting}
      />
    </div>
  );
}

function PlayerStatus({ sources }: { sources: ReturnType<typeof useSources> }) {
  let title = "Loading sources…";
  let detail: string | null = null;
  if (sources.loadError) {
    title = "Couldn’t load sources";
    detail = "Is the NotFlix API running?";
  } else if (!sources.loading && sources.languages.length === 0) {
    title = "No source for this episode yet";
    detail =
      "No provider has this episode. For German sources, check the AniWorld and AnimeToast pages under “More options” on the show’s page.";
  } else if (sources.searching) {
    title = "Looking for a direct stream…";
    const checked = sources.candidates.filter((o) => sources.resolutionOf(o)).length;
    detail = `${checked} of ${sources.candidates.length} sources checked`;
  } else if (sources.resolving) {
    title = `Loading ${sources.active?.label}…`;
  } else if (sources.error) {
    title = `${sources.active?.label ?? "Source"} failed`;
    detail = `${sources.error}. Pick another source or language below.`;
  } else if (!sources.loading && !sources.active) {
    title = `No working ${LANGUAGE_LABELS[sources.language]} source`;
    detail = "Try another language below.";
  }
  return (
    <div className="grid h-full place-items-center p-6 text-center text-muted">
      <div>
        <p className="text-lg font-semibold text-white">{title}</p>
        {detail && <p className="mt-2 text-sm">{detail}</p>}
      </div>
    </div>
  );
}

function SegmentInfo({
  segments,
  embedded,
  detecting,
}: {
  segments: SkipSegment[];
  embedded: boolean;
  detecting: boolean;
}) {
  if (segments.length === 0) {
    return (
      <p className="mt-4 text-sm text-muted">
        {detecting
          ? "Detecting intro & outro in the background…"
          : "Intro/outro not detected yet. It’s detected automatically while a direct stream plays, or under “More options” on the show’s page."}
      </p>
    );
  }
  return (
    <div className="mt-4 text-sm text-muted">
      <div className="flex flex-wrap gap-3">
        {segments.map((s) => (
          <span key={s.kind} className="rounded bg-surface-raised px-3 py-1">
            {s.kind === "opening" ? "Intro" : "Outro"} {formatTime(s.start_s)}–{formatTime(s.end_s)}
          </span>
        ))}
      </div>
      {embedded && (
        <p className="mt-2">
          Embedded players can’t be read or controlled from NotFlix, so “Skip Intro” and starting
          the next episode automatically only work with direct sources.
        </p>
      )}
    </div>
  );
}
