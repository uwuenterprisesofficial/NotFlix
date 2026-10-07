"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { displayTitle } from "@/lib/format";
import { allowedImage } from "@/lib/images";
import type { Playlist, PlaylistItem } from "@/lib/types";
import { AirTime } from "../AirTime";
import { useT } from "../I18nProvider";

/** Send a change; the answer is the whole playlist again. */
async function change(path: string, method: string, body?: unknown): Promise<Playlist | null> {
  const res = await fetch(`/api/me/playlist${path}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  }).catch(() => null);
  return res?.ok ? res.json() : null;
}

/** The playlist: reorder, remove, play, and the automatic airing shows. */
export function PlaylistEditor({ initial }: { initial: Playlist }) {
  const { t } = useT();
  const [playlist, setPlaylist] = useState(initial);
  const [failed, setFailed] = useState(false);

  async function apply(optimistic: Playlist, request: Promise<Playlist | null>) {
    const before = playlist;
    setPlaylist(optimistic);
    const result = await request;
    setFailed(!result);
    setPlaylist(result ?? before);
  }

  function move(index: number, by: number) {
    const items = [...playlist.items];
    const [item] = items.splice(index, 1);
    items.splice(index + by, 0, item);
    void apply(
      { ...playlist, items },
      change("/order", "PUT", { anime_ids: items.map((i) => i.anime.id) }),
    );
  }

  function remove(id: number) {
    void apply(
      { ...playlist, items: playlist.items.filter((i) => i.anime.id !== id) },
      change(`/${id}`, "DELETE"),
    );
  }

  function setAuto(on: boolean) {
    void apply({ ...playlist, auto_airing: on }, change("/settings", "PUT", { auto_airing: on }));
  }

  const first = playlist.items.find((i) => i.episode !== null);
  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-start justify-between gap-4 rounded-lg bg-surface-raised p-4">
        <label className="flex max-w-xl cursor-pointer gap-3">
          <input
            type="checkbox"
            checked={playlist.auto_airing}
            onChange={(e) => setAuto(e.target.checked)}
            className="mt-1 size-4 accent-brand"
          />
          <span>
            <span className="font-semibold">{t("playlist.autoAiring")}</span>
            <span className="mt-0.5 block text-sm text-muted">{t("playlist.autoAiringInfo")}</span>
          </span>
        </label>
        {first && (
          <Link
            href={`/watch/${first.anime.id}/${first.episode}`}
            className="rounded bg-white px-5 py-2 font-semibold text-black hover:bg-white/80"
          >
            ▶ {t("playlist.playAll")}
          </Link>
        )}
      </div>
      {failed && <p className="mt-3 text-sm text-red-400">{t("playlist.failed")}</p>}

      {playlist.items.length === 0 ? (
        <p className="mt-8 text-muted">{t("playlist.empty")}</p>
      ) : (
        <ol className="mt-6 space-y-2">
          {playlist.items.map((item, i) => (
            <Row
              key={item.anime.id}
              item={item}
              index={i}
              last={i === playlist.items.length - 1}
              onMove={(by) => move(i, by)}
              onRemove={() => remove(item.anime.id)}
            />
          ))}
        </ol>
      )}
    </div>
  );
}

function Row({
  item,
  index,
  last,
  onMove,
  onRemove,
}: {
  item: PlaylistItem;
  index: number;
  last: boolean;
  onMove: (by: number) => void;
  onRemove: () => void;
}) {
  const { t } = useT();
  const { anime, episode } = item;
  const picture = allowedImage(anime.picture_url);
  const button =
    "grid size-8 place-items-center rounded text-muted hover:bg-white/10 hover:text-white disabled:opacity-30 disabled:hover:bg-transparent";
  return (
    <li className="flex items-center gap-3 rounded-lg bg-surface-raised p-2 pr-3">
      <span className="w-6 shrink-0 text-center text-sm font-bold text-muted">{index + 1}</span>
      {picture ? (
        <Image
          src={picture}
          alt=""
          width={48}
          height={68}
          className="h-[68px] w-12 shrink-0 rounded object-cover"
        />
      ) : (
        <span className="h-[68px] w-12 shrink-0 rounded bg-white/10" />
      )}
      <div className="min-w-0 flex-1">
        <Link href={`/anime/${anime.id}`} className="line-clamp-1 font-semibold hover:underline">
          {displayTitle(anime)}
        </Link>
        <p className="text-sm text-muted">
          {episode !== null ? (
            t("playlist.episode", { episode })
          ) : anime.next_episode && anime.next_episode_at ? (
            <>
              {t("playlist.waitingFor", { episode: anime.next_episode })}{" "}
              <AirTime at={anime.next_episode_at} />
            </>
          ) : (
            t("playlist.waiting")
          )}
          {item.auto && (
            <span className="ml-2 rounded bg-brand/80 px-1.5 py-0.5 text-[10px] font-bold text-white uppercase">
              {t("playlist.newEpisodes")}
            </span>
          )}
        </p>
      </div>
      {episode !== null && (
        <Link
          href={`/watch/${anime.id}/${episode}`}
          className="rounded bg-white px-3 py-1 text-sm font-semibold text-black hover:bg-white/80"
        >
          ▶ {t("playlist.play")}
        </Link>
      )}
      <button
        onClick={() => onMove(-1)}
        disabled={index === 0}
        title={t("playlist.moveUp")}
        aria-label={t("playlist.moveUp")}
        className={button}
      >
        ▲
      </button>
      <button
        onClick={() => onMove(1)}
        disabled={last}
        title={t("playlist.moveDown")}
        aria-label={t("playlist.moveDown")}
        className={button}
      >
        ▼
      </button>
      <button
        onClick={onRemove}
        title={t("playlist.remove")}
        aria-label={t("playlist.remove")}
        className={button}
      >
        ✕
      </button>
    </li>
  );
}

/** "+ Playlist" on a show's page: adds it to (or takes it off) the playlist. */
export function PlaylistButton({ animeId, large = false }: { animeId: number; large?: boolean }) {
  const { t } = useT();
  const [inList, setInList] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/me/playlist")
      .then((r) => (r.ok ? (r.json() as Promise<Playlist>) : null))
      .catch(() => null)
      .then((p) => !cancelled && p && setInList(p.items.some((i) => i.anime.id === animeId)));
    return () => {
      cancelled = true;
    };
  }, [animeId]);

  async function toggle() {
    setBusy(true);
    const result = inList
      ? await change(`/${animeId}`, "DELETE")
      : await change("", "POST", { anime_id: animeId });
    if (result) setInList(result.items.some((i) => i.anime.id === animeId));
    setBusy(false);
  }

  return (
    <button
      onClick={toggle}
      disabled={busy || inList === null}
      title={inList ? t("playlist.removeTitle") : t("playlist.addTitle")}
      className={
        large
          ? "inline-flex items-center gap-2 rounded bg-white/20 px-5 py-2 font-semibold backdrop-blur hover:bg-white/30 disabled:opacity-60"
          : "rounded bg-surface-raised px-3 py-1 hover:bg-neutral-700 disabled:opacity-60"
      }
    >
      {inList ? `✓ ${t("playlist.added")}` : `＋ ${t("playlist.add")}`}
    </button>
  );
}
