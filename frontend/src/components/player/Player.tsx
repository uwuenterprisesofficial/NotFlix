"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { formatTime } from "@/lib/format";
import type { ListProvider, Progress, SkipSegment } from "@/lib/types";
import { useT } from "../I18nProvider";
import { streamOf, TogetherBar } from "../together/TogetherBar";
import { useWatchParty } from "../together/WatchParty";
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
  resumeAt = null,
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
  /** Where this episode was stopped last time (signed in, direct streams). */
  resumeAt?: number | null;
}) {
  const { t } = useT();
  const router = useRouter();
  const sources = useSources(animeId, episode, { ...via, server });
  const [autoSkip, setAutoSkip] = useAutoSkip();
  const [autoNext, setAutoNext] = useStoredValue<"0" | "1">("notflix:autonext", "1");
  // Episodes watched on MyAnimeList: a count, so unwatching sets it to the episode before.
  const [progress, setProgress] = useState(watched);
  const [saving, setSaving] = useState(false);
  const [saveFailed, setSaveFailed] = useState(false);
  // Linked lists the last change didn't reach (the others have it).
  const [partial, setPartial] = useState<ListProvider[] | null>(null);
  const savingNow = useRef(false);
  const isWatched = episode <= progress;
  const autoMarked = useRef(false);
  // Where playback is, so a replacement for a stream that broke continues from there.
  const position = useRef(resumeAt ?? 0);
  const playing = useRef(false);
  const party = useWatchParty();
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
  if (party) nextParams.set("together", String(party.connectionId));
  const nextHref = `/watch/${animeId}/${episode + 1}${nextParams.size ? `?${nextParams}` : ""}`;
  const analysis = useAutoAnalysis(animeId, episode, signedIn);
  // Timestamps from the source itself match its exact cut; analysed ones are the fallback
  // (including ones the analysis started while watching finds).
  const skipSegments = sources.resolved?.skip_segments.length
    ? sources.resolved.skip_segments
    : (analysis.segments ?? segments);

  // Watch Together: this page starts its episode in the room (the partner follows), unless the
  // room is on it already (e.g. this page followed the partner).
  const claimed = useRef(false);
  useEffect(() => {
    if (!party?.ready || claimed.current) return;
    claimed.current = true;
    const s = party.state;
    if (s && s.anime_id === animeId && s.episode === episode) return;
    party.send({
      action: "load",
      anime_id: animeId,
      episode,
      position: position.current,
      playing: playing.current,
      stream: streamOf(sources),
    });
  }, [party, animeId, episode, sources]);

  /** The first to play the episode tells the room which stream, so the partner can take it. */
  function shareStream() {
    const s = party?.state;
    const mine = streamOf(sources);
    if (!party || !mine || !s || s.anime_id !== animeId || s.episode !== episode) return;
    if (s.stream?.label) return; // the partner's (they may take ours from the bar instead)
    party.send({
      action: "stream",
      anime_id: animeId,
      episode,
      position: position.current,
      stream: mine,
    });
  }

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
      setPartial(saved.failed?.length ? saved.failed : null);
    } else {
      setSaveFailed(true);
    }
    savingNow.current = false;
    setSaving(false);
  }

  /** Remember where playback is, for resuming (on the user's account, so any device). */
  function savePosition(at: number, duration: number, final: boolean) {
    if (!signedIn) return;
    const url = `/api/anime/${animeId}/position`;
    const body = JSON.stringify({ episode, position_s: at, duration_s: duration });
    // The tab may be closing: a beacon still goes out.
    if (final && navigator.sendBeacon?.(url, new Blob([body], { type: "application/json" })))
      return;
    fetch(url, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body,
      keepalive: true,
    }).catch(() => {});
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
                next={
                  hasNext
                    ? { label: t("player.nextEpisode"), go: () => router.push(nextHref) }
                    : null
                }
                onNearEnd={autoMarkWatched}
                onStart={() => {
                  sources.started();
                  shareStream();
                  // Only direct streams can be analysed; this one is known to play.
                  analysis.start(sources.language);
                }}
                onFail={() => sources.failStream(stream.url)}
                resumeFrom={() => position.current}
                onPosition={(t) => (position.current = t)}
                resumedAt={resumeAt}
                onSave={savePosition}
                onPlayState={(p) => (playing.current = p)}
                sync={party ? { party, animeId, episode } : null}
              />
            )}
            {stream?.kind === "embed" && (
              <iframe
                key={stream.url}
                src={stream.url}
                title={t("player.episodeTitle", { episode })}
                // No sandbox: hosters (VOE, Doodstream, ...) detect it and refuse to play. Browsers
                // already block top-level redirects from cross-origin frames without a user click.
                allow="autoplay; fullscreen; encrypted-media; picture-in-picture"
                allowFullScreen
                onLoad={() => {
                  sources.started();
                  shareStream();
                }}
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
                ▶ {t("player.nextEpisode")}
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
            {sources.loading && (
              <span className="text-xs text-muted">{t("player.loadingMore")}</span>
            )}
          </div>
          <div className="ml-auto">
            <StreamMenu sources={sources} />
          </div>
        </div>
      )}

      <TogetherBar
        party={party}
        animeId={animeId}
        episode={episode}
        sources={sources}
        signedIn={signedIn}
      />

      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
        {stream?.kind === "direct" && (
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={autoSkip}
              onChange={(e) => setAutoSkip(e.target.checked)}
              className="accent-brand"
            />
            {t("player.autoSkip")}
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
            {t("player.autoNext")}
          </label>
        )}
        <div className="ml-auto flex items-center gap-2">
          {partial && (
            <span className="text-xs text-amber-400">
              {t("player.notSavedTo", {
                lists: partial.map((p) => t(`list.${p}`)).join(", "),
              })}
            </span>
          )}
          {signedIn && (
            <button
              onClick={() => setWatched(!isWatched)}
              disabled={saving}
              aria-pressed={isWatched}
              title={
                !isWatched
                  ? undefined
                  : progress > episode
                    ? t("player.unwatchBack", { episode: episode - 1 })
                    : t("player.unwatchTitle")
              }
              className="group/watched rounded bg-surface-raised px-3 py-1 hover:bg-neutral-700 disabled:opacity-60"
            >
              {saving ? (
                t("player.saving")
              ) : saveFailed ? (
                t("player.saveFailed")
              ) : isWatched ? (
                <>
                  <span className="group-hover/watched:hidden">{t("player.watched")}</span>
                  <span className="hidden group-hover/watched:inline">{t("player.unwatch")}</span>
                </>
              ) : (
                t("player.markWatched")
              )}
            </button>
          )}
          {hasNext && (
            <Link href={nextHref} className="rounded bg-white px-3 py-1 font-semibold text-black">
              {t("player.nextEpisodeShort")}
            </Link>
          )}
        </div>
      </div>

      <SegmentInfo
        segments={skipSegments}
        embedded={stream?.kind === "embed"}
        detecting={analysis.detecting}
        onStopDetecting={analysis.stop}
      />
    </div>
  );
}

function PlayerStatus({ sources }: { sources: ReturnType<typeof useSources> }) {
  const { t } = useT();
  let title = t("player.loadingSources");
  let detail: string | null = null;
  if (sources.loadError) {
    title = t("player.loadFailed");
    detail = t("player.apiRunning");
  } else if (!sources.loading && sources.languages.length === 0) {
    title = t("player.noSource");
    detail = t("player.noSourceInfo");
  } else if (sources.searching) {
    title = t("player.lookingDirect");
    const checked = sources.candidates.filter((o) => sources.resolutionOf(o)).length;
    detail = t("player.checked", { checked, total: sources.candidates.length });
  } else if (sources.resolving) {
    title = t("player.loadingSource", { label: sources.active?.label ?? "" });
  } else if (sources.error) {
    title = t("player.sourceFailed", { label: sources.active?.label ?? t("player.source") });
    detail = t("player.pickAnother", { error: sources.error });
  } else if (!sources.loading && !sources.active) {
    title = t("player.noWorking", { language: t(`lang.${sources.language}`) });
    detail = t("player.tryLanguage");
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
  onStopDetecting,
}: {
  segments: SkipSegment[];
  embedded: boolean;
  detecting: boolean;
  onStopDetecting: () => void;
}) {
  const { t } = useT();
  if (segments.length === 0) {
    return (
      <p className="mt-4 text-sm text-muted">
        {detecting ? (
          <>
            {t("player.detecting")}{" "}
            <button onClick={onStopDetecting} className="underline hover:text-white">
              {t("player.stop")}
            </button>
          </>
        ) : (
          t("player.notDetected")
        )}
      </p>
    );
  }
  return (
    <div className="mt-4 text-sm text-muted">
      <div className="flex flex-wrap gap-3">
        {segments.map((s) => (
          <span key={s.kind} className="rounded bg-surface-raised px-3 py-1">
            {s.kind === "opening" ? t("player.intro") : t("player.outro")} {formatTime(s.start_s)}–
            {formatTime(s.end_s)}
            {s.source === "aniskip" && <span className="ml-1 text-xs opacity-70">(AniSkip)</span>}
          </span>
        ))}
      </div>
      {embedded && <p className="mt-2">{t("player.embedInfo")}</p>}
    </div>
  );
}
