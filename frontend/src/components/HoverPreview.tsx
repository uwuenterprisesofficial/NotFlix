"use client";

import type Hls from "hls.js";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { displayTitle, nextEpisode, relativeTime, seasonText } from "@/lib/format";
import { formatNumber, genreName, mediaTypeName } from "@/lib/i18n";
import { allowedImage } from "@/lib/images";
import type { AnimeCard, Preview, Progress } from "@/lib/types";
import { useNow } from "@/lib/useNow";
import { useStoredValue } from "./player/useStoredValue";
import { useT } from "./I18nProvider";
import { PredictionBadge } from "./PredictionBadge";

// One request per show and language per visit (null: no preview).
const previews = new Map<string, Promise<Preview | null>>();

function loadPreview(animeId: number, lang: string): Promise<Preview | null> {
  const key = `${animeId}:${lang}`;
  let request = previews.get(key);
  if (!request) {
    request = fetch(`/api/anime/${animeId}/preview?lang=${lang}`)
      .then((res) => (res.ok ? (res.json() as Promise<Preview>) : null))
      .catch(() => null);
    previews.set(key, request);
  }
  return request;
}

const MARGIN = 12;
const MIN_WIDTH = 320;
const MAX_WIDTH = 420;

/** Where the enlarged card goes: centred on the poster, kept inside the window. */
export function previewPosition(rect: DOMRect) {
  const width = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, rect.width * 2));
  const left = Math.min(
    Math.max(MARGIN, rect.left + rect.width / 2 - width / 2),
    window.innerWidth - width - MARGIN,
  );
  const mediaHeight = (width * 9) / 16;
  const top = Math.max(
    window.scrollY + 72, // below the navigation bar
    rect.top + window.scrollY + rect.height / 2 - mediaHeight / 2 - 24,
  );
  return { left: left + window.scrollX, top, width };
}

/** The Netflix-style enlarged card shown while hovering a poster. */
export function HoverPreview({
  anime,
  position,
  onClose,
}: {
  anime: AnimeCard;
  position: { left: number; top: number; width: number };
  onClose: () => void;
}) {
  const { t, lang } = useT();
  const router = useRouter();
  const now = useNow();
  const video = useRef<HTMLVideoElement>(null);
  const [shown, setShown] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useStoredValue<"1" | "0">("notflix:preview-muted", "1");
  const [progress, setProgress] = useState<Progress | null>(anime.progress);
  const [adding, setAdding] = useState<"idle" | "busy" | "done" | "failed">("idle");

  useEffect(() => {
    const frame = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  const upcoming = anime.status === "not_yet_aired";
  useEffect(() => {
    if (upcoming) return;
    let cancelled = false;
    loadPreview(anime.id, lang).then((p) => !cancelled && setPreview(p));
    return () => {
      cancelled = true;
    };
  }, [anime.id, lang, upcoming]);

  // Attach the stream: natively (MP4, Safari's HLS) or through hls.js.
  useEffect(() => {
    const el = video.current;
    if (!el || !preview) return;
    const isHls = preview.format === "hls";
    if (!isHls || el.canPlayType("application/vnd.apple.mpegurl")) {
      el.src = preview.url;
      return () => el.removeAttribute("src");
    }
    let hls: Hls | undefined;
    let cancelled = false;
    import("hls.js").then(({ default: HlsClass }) => {
      if (cancelled || !HlsClass.isSupported()) return;
      hls = new HlsClass({ startPosition: preview.start_s, maxBufferLength: 20 });
      hls.loadSource(preview.url);
      hls.attachMedia(el);
    });
    return () => {
      cancelled = true;
      hls?.destroy();
    };
  }, [preview]);

  async function addToPlan() {
    setAdding("busy");
    const res = await fetch(`/api/anime/${anime.id}/list`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ status: "plan_to_watch" }),
    }).catch(() => null);
    // Not signed in, or a guest (no list): sign in with one.
    if (res?.status === 401 || res?.status === 403) {
      router.push("/login");
      return;
    }
    if (res?.ok) {
      setProgress(await res.json());
      setAdding("done");
      router.refresh(); // e.g. the My List row
    } else {
      setAdding("failed");
    }
  }

  const picture = allowedImage(anime.picture_url);
  const year = anime.start_season?.split(" ")[1];
  const onList = progress && progress.status;
  const playHref = `/watch/${anime.id}/${nextEpisode({ ...anime, progress })}`;
  const statusText =
    anime.status === "currently_airing"
      ? t("preview.airing")
      : anime.status === "not_yet_aired"
        ? t("preview.upcoming")
        : anime.status === "finished_airing"
          ? t("preview.finished")
          : null;

  return createPortal(
    <div
      role="dialog"
      aria-label={displayTitle(anime)}
      onPointerLeave={onClose}
      style={{ left: position.left, top: position.top, width: position.width }}
      className={`absolute z-[60] origin-center overflow-hidden rounded-lg bg-surface-raised shadow-2xl ring-1 ring-white/10 transition duration-200 ease-out ${shown ? "scale-100 opacity-100" : "scale-75 opacity-0"}`}
    >
      <div className="relative aspect-video bg-black">
        {picture && (
          <Image
            src={picture}
            alt=""
            fill
            sizes={`${position.width}px`}
            className="object-cover object-[50%_20%]"
          />
        )}
        {preview && (
          <video
            ref={video}
            muted={muted === "1"}
            autoPlay
            playsInline
            loop
            onLoadedMetadata={(e) => {
              if (preview.start_s && e.currentTarget.currentTime < 1)
                e.currentTarget.currentTime = preview.start_s;
            }}
            onPlaying={() => setPlaying(true)}
            className={`absolute inset-0 h-full w-full object-cover transition-opacity duration-500 ${playing ? "opacity-100" : "opacity-0"}`}
          />
        )}
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 to-transparent p-3 pt-10">
          <p className="line-clamp-2 text-lg leading-tight font-bold drop-shadow">
            {displayTitle(anime)}
          </p>
        </div>
        {preview && playing && (
          <button
            onClick={() => setMuted(muted === "1" ? "0" : "1")}
            aria-label={muted === "1" ? t("preview.mute") : t("preview.unmute")}
            title={muted === "1" ? t("preview.mute") : t("preview.unmute")}
            className="absolute right-3 bottom-3 grid size-8 place-items-center rounded-full border border-white/60 bg-black/50 text-sm hover:border-white"
          >
            {muted === "1" ? "🔇" : "🔊"}
          </button>
        )}
      </div>

      <div className="space-y-2.5 p-3.5">
        <div className="flex items-center gap-2">
          {!upcoming && (
            <Link
              href={playHref}
              aria-label={t("preview.play")}
              title={t("preview.play")}
              className="grid size-9 place-items-center rounded-full bg-white text-black hover:bg-white/80"
            >
              ▶
            </Link>
          )}
          {onList ? (
            <span
              title={t("preview.onList", { status: t(`list.${progress!.status}`) })}
              aria-label={t("preview.onList", { status: t(`list.${progress!.status}`) })}
              className="grid size-9 place-items-center rounded-full border-2 border-white/40 text-sm"
            >
              ✓
            </span>
          ) : (
            <button
              onClick={addToPlan}
              disabled={adding === "busy"}
              aria-label={t("preview.add")}
              title={adding === "failed" ? t("preview.addFailed") : t("preview.add")}
              className={`grid size-9 place-items-center rounded-full border-2 text-lg hover:border-white disabled:opacity-50 ${adding === "failed" ? "border-red-400" : "border-white/40"}`}
            >
              +
            </button>
          )}
          {adding === "done" && <span className="text-xs text-muted">{t("preview.added")}</span>}
          {adding === "failed" && (
            <span className="text-xs text-red-400">{t("preview.addFailed")}</span>
          )}
          <Link
            href={`/anime/${anime.id}`}
            aria-label={t("preview.more")}
            title={t("preview.more")}
            className="ml-auto grid size-9 place-items-center rounded-full border-2 border-white/40 hover:border-white"
          >
            ⌄
          </Link>
        </div>

        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-sm">
          <PredictionBadge prediction={anime.prediction} />
          {anime.mean !== null && (
            <span className="font-semibold text-green-400">★ {formatNumber(lang, anime.mean)}</span>
          )}
          {progress?.score ? (
            <span className="text-neutral-300">
              {t("stats.you")} {progress.score}
            </span>
          ) : null}
          {anime.media_type && (
            <span className="rounded border border-white/40 px-1 text-[11px] leading-4">
              {mediaTypeName(lang, anime.media_type)}
            </span>
          )}
          {anime.num_episodes ? (
            <span className="text-neutral-300">
              {t("anime.episodes", { count: anime.num_episodes })}
            </span>
          ) : null}
          {year && <span className="text-neutral-400">{year}</span>}
        </div>

        {(statusText || anime.next_episode_at) && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {statusText && (
              <span
                className={`rounded px-1.5 py-0.5 font-semibold ${anime.status === "currently_airing" ? "bg-brand/80 text-white" : "bg-white/10"}`}
              >
                {statusText}
              </span>
            )}
            {anime.next_episode && anime.next_episode_at && now !== null && (
              <span className="text-neutral-300">
                {t("preview.nextEpisode", {
                  episode: anime.next_episode,
                  when: relativeTime(lang, anime.next_episode_at, now),
                })}
              </span>
            )}
            {anime.start_season && anime.status === "not_yet_aired" && (
              <span className="text-neutral-400">{seasonText(t, anime.start_season)}</span>
            )}
          </div>
        )}

        {anime.genres.length > 0 && (
          <p className="text-xs text-neutral-300">
            {anime.genres
              .slice(0, 4)
              .map((g) => genreName(lang, g))
              .join(" • ")}
          </p>
        )}

        {progress?.status === "watching" && anime.num_episodes ? (
          <div className="flex items-center gap-2 text-xs text-muted">
            <span className="h-1 flex-1 overflow-hidden rounded bg-white/20">
              <span
                className="block h-full bg-brand"
                style={{
                  width: `${Math.min(100, (progress.episodes_watched / anime.num_episodes) * 100)}%`,
                }}
              />
            </span>
            {progress.episodes_watched}/{anime.num_episodes}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}
