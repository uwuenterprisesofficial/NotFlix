"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { formatTime } from "@/lib/format";
import { LANGUAGE_LABELS } from "@/lib/languages";
import type { SkipSegment, Stream } from "@/lib/types";
import { DirectVideo } from "./DirectVideo";
import { useAutoSkip } from "./useAutoSkip";
import { useSources } from "./useSources";

type SaveState = "idle" | "saving" | "saved" | "error";

export function Player({
  animeId,
  episode,
  segments,
  hasNext,
  signedIn,
  watched,
}: {
  animeId: number;
  episode: number;
  segments: SkipSegment[];
  hasNext: boolean;
  signedIn: boolean;
  watched: number;
}) {
  const router = useRouter();
  const sources = useSources(animeId, episode);
  const [streamChoice, setStreamChoice] = useState<Record<string, number>>({});
  const [autoSkip, setAutoSkip] = useAutoSkip();
  const [saveState, setSaveState] = useState<SaveState>(episode <= watched ? "saved" : "idle");
  const saving = useRef(false);
  const autoMarked = useRef(false);
  const nextHref = `/watch/${animeId}/${episode + 1}`;

  const streams = sources.resolved?.streams ?? [];
  const streamIndex = sources.active ? (streamChoice[sources.active.id] ?? 0) : 0;
  const stream: Stream | undefined = streams[streamIndex] ?? streams[0];
  // Timestamps from the source itself match its exact cut; analysed ones are the fallback.
  const skipSegments = sources.resolved?.skip_segments.length
    ? sources.resolved.skip_segments
    : segments;

  async function markWatched() {
    if (!signedIn || saving.current || saveState === "saved") return;
    saving.current = true;
    setSaveState("saving");
    const res = await fetch(`/api/anime/${animeId}/progress`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ episodes_watched: episode }),
    });
    setSaveState(res.ok ? "saved" : "error");
    saving.current = false;
  }

  function autoMarkWatched() {
    if (autoMarked.current) return;
    autoMarked.current = true;
    void markWatched();
  }

  return (
    <div>
      <div className="relative aspect-video w-full overflow-hidden rounded-lg bg-black">
        {stream?.kind === "direct" && (
          <DirectVideo
            key={stream.url}
            stream={stream}
            segments={skipSegments}
            autoSkip={autoSkip}
            nextEpisodeLabel={hasNext ? "Next Episode ›" : null}
            onSkipEnding={hasNext ? () => router.push(nextHref) : null}
            onNearEnd={autoMarkWatched}
          />
        )}
        {stream?.kind === "embed" && (
          <iframe
            key={stream.url}
            src={stream.url}
            title={`Episode ${episode}`}
            // No popups or top-level redirects from third-party embed pages.
            sandbox="allow-scripts allow-same-origin allow-presentation"
            allow="autoplay; fullscreen; encrypted-media; picture-in-picture"
            allowFullScreen
            referrerPolicy="no-referrer"
            className="h-full w-full border-0"
          />
        )}
        {!stream && <PlayerStatus sources={sources} />}
      </div>

      {sources.languages.length > 0 && (
        <div className="mt-4 space-y-3 text-sm">
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Language">
            {sources.languages.map((lang) => (
              <button
                key={lang}
                role="tab"
                aria-selected={lang === sources.language}
                onClick={() => sources.setLanguage(lang)}
                className={`rounded-full px-4 py-1 font-semibold ${lang === sources.language ? "bg-white text-black" : "bg-surface-raised hover:bg-neutral-700"}`}
              >
                {LANGUAGE_LABELS[lang]}
              </button>
            ))}
            {sources.loading && (
              <span className="self-center text-xs text-muted">Loading more sources…</span>
            )}
          </div>
          <div className="flex flex-wrap gap-2" aria-label="Source">
            {sources.candidates.map((o) => (
              <button
                key={o.id}
                onClick={() => sources.choose(o.id)}
                title={sources.failed(o) ? "This source failed" : undefined}
                className={`rounded px-3 py-1 ${o.id === sources.active?.id ? "bg-brand" : "bg-surface-raised hover:bg-neutral-700"} ${sources.failed(o) ? "line-through opacity-50" : ""}`}
              >
                {o.label}
              </button>
            ))}
            {streams.length > 1 &&
              streams.map((s, i) => (
                <button
                  key={s.url}
                  onClick={() =>
                    sources.active && setStreamChoice((c) => ({ ...c, [sources.active!.id]: i }))
                  }
                  className={`rounded border px-3 py-1 ${s === stream ? "border-white" : "border-white/20 text-muted hover:text-white"}`}
                >
                  {s.label}
                </button>
              ))}
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
            Auto-skip intro &amp; outro
          </label>
        )}
        <div className="ml-auto flex gap-2">
          {signedIn && (
            <button
              onClick={markWatched}
              disabled={saveState === "saving" || saveState === "saved"}
              className="rounded bg-surface-raised px-3 py-1 hover:bg-neutral-700 disabled:opacity-60"
            >
              {
                {
                  idle: "Mark as watched",
                  saving: "Saving…",
                  saved: "✓ Watched",
                  error: "Retry saving",
                }[saveState]
              }
            </button>
          )}
          {hasNext && (
            <Link href={nextHref} className="rounded bg-white px-3 py-1 font-semibold text-black">
              Next episode ›
            </Link>
          )}
        </div>
      </div>

      <SegmentInfo segments={skipSegments} embedded={stream?.kind === "embed"} />
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
      "No provider has this episode. For German sources, check the AniWorld mapping on the show’s page.";
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

function SegmentInfo({ segments, embedded }: { segments: SkipSegment[]; embedded: boolean }) {
  if (segments.length === 0) {
    return (
      <p className="mt-4 text-sm text-muted">
        Intro/outro not detected yet — run the analyser from the show’s page.
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
          Embedded players can’t be controlled from NotFlix, so skip buttons only work with direct
          sources.
        </p>
      )}
    </div>
  );
}
