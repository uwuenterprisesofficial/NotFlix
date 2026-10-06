"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { relativeTime } from "@/lib/format";
import type { T } from "@/lib/i18n";
import type {
  FriendRecommendation,
  Progress,
  ShowRecommendations,
} from "@/lib/types";
import { useT } from "../I18nProvider";
import { Avatar } from "../together/Avatar";

const MESSAGE_MAX = 300;

/** Where a friend is with a show: "Completed · 26/26 · ★ 8". */
export function progressText(
  t: T,
  progress: Progress,
  episodes: number | null,
): string {
  const parts = [
    t(`list.${progress.status}` as "list.watching"),
    `${progress.episodes_watched}/${episodes ?? "?"}`,
  ];
  if (progress.score) parts.push(`★ ${progress.score}`);
  return parts.join(" · ");
}

/** On a show's page: the friends who recommended it to the user, with their notes. */
export function RecommendedBy({
  received,
}: {
  received: FriendRecommendation[];
}) {
  const { t, lang } = useT();
  if (received.length === 0) return null;
  return (
    <ul className="mt-4 space-y-2">
      {received.map((r) => (
        <li
          key={r.id}
          className="flex items-start gap-3 rounded-lg bg-surface-raised p-3"
        >
          <Avatar person={r.person} size={32} />
          <div className="min-w-0 text-sm">
            <p>
              <span className="font-semibold">
                {t("friends.recommendsThis", { name: r.person.name })}
              </span>{" "}
              <span className="text-muted">
                · {relativeTime(lang, r.created_at)}
              </span>
            </p>
            {r.message && (
              <p className="mt-0.5 text-neutral-200">“{r.message}”</p>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

/**
 * On a show's page: a button to recommend it to friends, with a note. Friends who have it on their list say where they
 * are with it; ones it was recommended to already say when.
 */
export function RecommendToFriend({
  animeId,
  title,
  episodes,
  initial,
}: {
  animeId: number;
  title: string;
  episodes: number | null;
  initial: ShowRecommendations;
}) {
  const { t, lang } = useT();
  const dialog = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState(initial);
  const [chosen, setChosen] = useState<Set<number>>(new Set());
  const [message, setMessage] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "failed" | "empty">(
    "idle",
  );
  const [sentTo, setSentTo] = useState<number | null>(null);
  // The form only exists while the dialog is open (nothing for the browser to restore).
  const [isOpen, setIsOpen] = useState(false);

  function open() {
    setChosen(new Set());
    setMessage("");
    setState("idle");
    setSentTo(null);
    setIsOpen(true);
    dialog.current?.showModal();
  }

  function toggle(connectionId: number) {
    if (state === "empty") setState("idle");
    setChosen((current) => {
      const next = new Set(current);
      if (next.has(connectionId)) next.delete(connectionId);
      else next.add(connectionId);
      return next;
    });
  }

  async function send() {
    if (chosen.size === 0) {
      setState("empty");
      return;
    }
    setState("sending");
    const res = await fetch("/api/friends/recommendations", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        anime_id: animeId,
        connection_ids: [...chosen],
        message,
      }),
    }).catch(() => null);
    if (!res?.ok) {
      setState("failed");
      return;
    }
    setData(await res.json());
    setSentTo(chosen.size);
    setState("idle");
  }

  return (
    <>
      <button
        type="button"
        onClick={open}
        className="inline-flex items-center gap-2 rounded bg-surface-raised px-3 py-1.5 text-sm font-semibold ring-1 ring-white/15 hover:bg-neutral-700"
      >
        <svg
          viewBox="0 0 24 24"
          className="size-4"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden
        >
          <path d="M4 12v7a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-7M16 6l-4-4-4 4M12 2v13" />
        </svg>
        {t("friends.recommend")}
      </button>
      <dialog
        ref={dialog}
        onClose={() => setIsOpen(false)}
        aria-labelledby="recommend-title"
        className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-lg bg-surface-raised p-0 text-white backdrop:bg-black/70"
      >
        {isOpen && (
          <div className="p-5">
            <h2 id="recommend-title" className="text-lg font-bold">
              {t("friends.recommendTitle", { title })}
            </h2>
            {data.friends.length === 0 ? (
              <>
                <p className="mt-3 text-sm text-muted">
                  {t("friends.noFriends")}
                </p>
                <div className="mt-5 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => dialog.current?.close()}
                    className="rounded px-4 py-2 text-sm font-semibold ring-1 ring-white/15 hover:ring-white/40"
                  >
                    {t("friends.close")}
                  </button>
                  <Link
                    href="/together"
                    className="rounded bg-brand px-4 py-2 text-sm font-semibold hover:bg-brand-dark"
                  >
                    {t("friends.inviteLink")}
                  </Link>
                </div>
              </>
            ) : (
              <>
                <ul className="mt-4 max-h-72 space-y-1 overflow-y-auto">
                  {data.friends.map((f) => (
                    <li key={f.connection_id}>
                      <label className="flex cursor-pointer items-center gap-3 rounded p-2 hover:bg-white/5">
                        <input
                          type="checkbox"
                          checked={chosen.has(f.connection_id)}
                          onChange={() => toggle(f.connection_id)}
                          className="size-4 accent-brand"
                        />
                        <Avatar person={f.person} size={32} />
                        <span className="min-w-0">
                          <span className="block font-semibold">
                            {f.person.name}
                          </span>
                          <span className="block text-xs text-muted">
                            {[
                              f.their_progress &&
                                progressText(t, f.their_progress, episodes),
                              f.recommended_at &&
                                t("friends.recommendedAgo", {
                                  when: relativeTime(lang, f.recommended_at),
                                }),
                            ]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </span>
                      </label>
                    </li>
                  ))}
                </ul>
                <label className="mt-4 block text-sm">
                  <span className="font-semibold">{t("friends.message")}</span>
                  <textarea
                    value={message}
                    maxLength={MESSAGE_MAX}
                    rows={3}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder={t("friends.messagePlaceholder")}
                    className="mt-1 block w-full resize-none rounded bg-neutral-800 px-3 py-2 ring-1 ring-white/10 outline-none focus:ring-white/40"
                  />
                  <span className="mt-1 block text-right text-xs text-muted">
                    {message.length}/{MESSAGE_MAX}
                  </span>
                </label>
                <p aria-live="polite" className="min-h-5 text-sm">
                  {sentTo !== null ? (
                    <span className="text-green-400">
                      {t("friends.sent", { count: sentTo })}
                    </span>
                  ) : state === "failed" ? (
                    <span className="text-red-400">{t("friends.failed")}</span>
                  ) : state === "empty" ? (
                    <span className="text-red-400">{t("friends.choose")}</span>
                  ) : null}
                </p>
                <div className="mt-3 flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => dialog.current?.close()}
                    className="rounded px-4 py-2 text-sm font-semibold ring-1 ring-white/15 hover:ring-white/40"
                  >
                    {sentTo !== null ? t("friends.close") : t("friends.cancel")}
                  </button>
                  {sentTo === null && (
                    <button
                      type="button"
                      onClick={send}
                      disabled={state === "sending"}
                      className="rounded bg-brand px-4 py-2 text-sm font-semibold hover:bg-brand-dark disabled:opacity-60"
                    >
                      {state === "sending"
                        ? t("friends.sending")
                        : t("friends.send")}
                    </button>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </dialog>
    </>
  );
}
