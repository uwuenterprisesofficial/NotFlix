"use client";

import { useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { relativeTime } from "@/lib/format";
import type { FriendRecommendation, FriendRecommendations } from "@/lib/types";
import { AnimeCard } from "../AnimeCard";
import { useT } from "../I18nProvider";
import { Avatar } from "../together/Avatar";
import { progressText } from "./RecommendToFriend";

const GRID =
  "mt-4 grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-x-3 gap-y-6 md:grid-cols-[repeat(auto-fill,minmax(11rem,1fr))]";

/**
 * What friends recommended to the user (with their notes; "Not for me" puts one aside) and what
 * the user recommended to them (with where each friend is with it; "Take back" removes it).
 * Opening it counts the new ones as seen; they stay marked "New" until the page is left.
 */
export function FriendRecommendationList({
  data,
}: {
  data: FriendRecommendations;
}) {
  const { t } = useT();
  const router = useRouter();
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  // Marked as seen right away, but still shown as new while the page is open.
  const [fresh] = useState(
    () => new Set(data.received.filter((r) => !r.seen).map((r) => r.id)),
  );

  useEffect(() => {
    if (data.unseen === 0) return;
    void fetch("/api/friends/recommendations/seen", { method: "POST" }).then(
      (res) => res.ok && router.refresh(), // the navigation's badge
    );
  }, [data.unseen, router]);

  async function remove(id: number) {
    setHidden((current) => new Set(current).add(id));
    const res = await fetch(`/api/friends/recommendations/${id}`, {
      method: "DELETE",
    }).catch(() => null);
    if (!res?.ok) {
      setHidden((current) => {
        const next = new Set(current);
        next.delete(id);
        return next;
      });
    }
  }

  const received = data.received.filter((r) => !hidden.has(r.id));
  const sent = data.sent.filter((r) => !hidden.has(r.id));

  return (
    <>
      <section id="friends" className="mt-10">
        <h2 className="flex items-center gap-3 text-xl font-bold">
          {t("friends.fromFriends")}
          {received.length > 0 && (
            <span className="text-sm font-normal text-muted">
              {received.length}
            </span>
          )}
        </h2>
        {received.length === 0 ? (
          <p className="mt-3 text-sm text-muted">
            {t("friends.fromFriendsEmpty")}
          </p>
        ) : (
          <div className={GRID}>
            {received.map((r) => (
              <Item
                key={r.id}
                item={r}
                action={{
                  label: t("friends.notForMe"),
                  onClick: () => remove(r.id),
                }}
              >
                <p className="flex items-center gap-2 text-xs">
                  <Avatar person={r.person} size={20} />
                  <span className="truncate font-semibold">
                    {t("friends.from", { name: r.person.name })}
                  </span>
                  {fresh.has(r.id) && (
                    <span className="rounded bg-brand px-1.5 py-px text-[10px] font-bold uppercase">
                      {t("friends.new")}
                    </span>
                  )}
                </p>
              </Item>
            ))}
          </div>
        )}
      </section>
      {sent.length > 0 && (
        <section id="recommended-by-me" className="mt-10">
          <h2 className="flex items-center gap-3 text-xl font-bold">
            {t("friends.youRecommended")}
            <span className="text-sm font-normal text-muted">
              {sent.length}
            </span>
          </h2>
          <div className={GRID}>
            {sent.map((r) => (
              <Item
                key={r.id}
                item={r}
                action={{
                  label: t("friends.takeBack"),
                  onClick: () => remove(r.id),
                }}
              >
                <p className="flex items-center gap-2 text-xs">
                  <Avatar person={r.person} size={20} />
                  <span className="truncate font-semibold">
                    {t("friends.to", { name: r.person.name })}
                  </span>
                </p>
                <p
                  className={`mt-1 text-xs ${r.dismissed ? "text-red-400" : "text-muted"}`}
                >
                  {r.dismissed
                    ? t("friends.putAside")
                    : r.their_progress
                      ? progressText(t, r.their_progress, r.anime.num_episodes)
                      : t("friends.notOnTheirList")}
                </p>
              </Item>
            ))}
          </div>
        </section>
      )}
    </>
  );
}

function Item({
  item,
  action,
  children,
}: {
  item: FriendRecommendation;
  action: { label: string; onClick: () => void };
  children: ReactNode;
}) {
  const { lang } = useT();
  return (
    <div>
      <AnimeCard anime={item.anime} fluid />
      <div className="mt-2 space-y-0.5">
        {children}
        {item.message && (
          <p
            className="line-clamp-3 text-xs text-neutral-300"
            title={item.message}
          >
            “{item.message}”
          </p>
        )}
        <p className="flex items-center gap-2 text-[11px] text-muted">
          {relativeTime(lang, item.created_at)} ·
          <button
            type="button"
            onClick={action.onClick}
            className="hover:text-white"
          >
            {action.label}
          </button>
        </p>
      </div>
    </div>
  );
}
