"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { formatTime } from "@/lib/format";
import type { SkipSegment, Source } from "@/lib/types";
import { DirectVideo } from "./DirectVideo";
import { useAutoSkip } from "./useAutoSkip";

type SaveState = "idle" | "saving" | "saved" | "error";

export function Player({
  animeId,
  episode,
  sources,
  segments,
  hasNext,
  signedIn,
  watched,
}: {
  animeId: number;
  episode: number;
  sources: Source[];
  segments: SkipSegment[];
  hasNext: boolean;
  signedIn: boolean;
  watched: number;
}) {
  const router = useRouter();
  const [sourceIndex, setSourceIndex] = useState(0);
  const [autoSkip, setAutoSkip] = useAutoSkip();
  const [saveState, setSaveState] = useState<SaveState>(episode <= watched ? "saved" : "idle");
  const saving = useRef(false);
  const autoMarked = useRef(false);
  const source = sources[sourceIndex];
  const nextHref = `/watch/${animeId}/${episode + 1}`;

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
        {source?.kind === "direct" && (
          <DirectVideo
            key={source.url}
            url={source.url}
            segments={segments}
            autoSkip={autoSkip}
            nextEpisodeLabel={hasNext ? "Next Episode ›" : null}
            onSkipEnding={hasNext ? () => router.push(nextHref) : null}
            onNearEnd={autoMarkWatched}
          />
        )}
        {source?.kind === "embed" && (
          <iframe
            key={source.url}
            src={source.url}
            title={`Episode ${episode}`}
            // No popups or top-level redirects from third-party embed pages.
            sandbox="allow-scripts allow-same-origin allow-presentation"
            allow="autoplay; fullscreen; encrypted-media; picture-in-picture"
            allowFullScreen
            referrerPolicy="no-referrer"
            className="h-full w-full border-0"
          />
        )}
        {!source && (
          <div className="grid h-full place-items-center p-6 text-center text-muted">
            <div>
              <p className="text-lg font-semibold text-white">No source for this episode yet</p>
              <p className="mt-2 text-sm">
                Add a row to the <code>stream_sources</code> table or implement a provider in{" "}
                <code>backend/app/providers</code>.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        {sources.length > 1 &&
          sources.map((s, i) => (
            <button
              key={s.url}
              onClick={() => setSourceIndex(i)}
              className={`rounded px-3 py-1 ${i === sourceIndex ? "bg-white text-black" : "bg-surface-raised hover:bg-neutral-700"}`}
            >
              {s.provider}
            </button>
          ))}
        {source?.kind === "direct" && (
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

      <SegmentInfo segments={segments} embedded={source?.kind === "embed"} />
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
