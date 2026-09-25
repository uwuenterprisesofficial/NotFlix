"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore, useTransition } from "react";
import { LOCALE } from "@/lib/i18n";
import type { Me } from "@/lib/types";
import { useT } from "./I18nProvider";
import { allowedImage } from "@/lib/images";

const noop = () => () => {};

export function UserMenu({ me }: { me: Me }) {
  // The server doesn't know the viewer's locale or timezone, so the local sync time is only
  // rendered after hydration.
  const hydrated = useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
  const { t, lang } = useT();
  const router = useRouter();
  const [syncing, setSyncing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  async function sync() {
    setSyncing(true);
    setMessage(null);
    const res = await fetch("/api/me/sync", { method: "POST" });
    setSyncing(false);
    if (res.ok) {
      const result = await res.json();
      const parts = [
        t("user.synced", { entries: result.entries, recommendations: result.recommendations }),
      ];
      if (result.adding_to_mal)
        parts.push(t("user.adding", { count: result.adding_to_mal, list: "MyAnimeList" }));
      if (result.adding_to_anilist)
        parts.push(t("user.adding", { count: result.adding_to_anilist, list: "AniList" }));
      if (result.skipped) parts.push(t("user.skipped", { count: result.skipped }));
      setMessage(parts.join(" · "));
      startTransition(() => router.refresh());
    } else {
      setMessage(t("user.syncFailed"));
    }
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    startTransition(() => router.refresh());
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      {message && <span className="hidden text-muted md:inline">{message}</span>}
      {me.guest ? (
        <>
          <span className="rounded bg-white/15 px-2 py-0.5 text-xs">{t("guest.badge")}</span>
          <Link
            href="/login"
            className="rounded border border-white/30 px-3 py-1 hover:bg-white/10"
          >
            {t("guest.signIn")}
          </Link>
        </>
      ) : (
        <button
          onClick={sync}
          disabled={syncing}
          className="rounded border border-white/30 px-3 py-1 hover:bg-white/10 disabled:opacity-50"
          title={
            !me.last_synced_at
              ? t("user.neverSynced")
              : hydrated
                ? t("user.lastSynced", {
                    when: new Date(me.last_synced_at).toLocaleString(LOCALE[lang]),
                  })
                : t("user.lastSyncedShort")
          }
        >
          {syncing ? t("user.syncing") : t("user.sync")}
        </button>
      )}
      <button onClick={logout} className="text-muted hover:text-white">
        {t("user.signOut")}
      </button>
      {allowedImage(me.picture) ? (
        <Image
          src={allowedImage(me.picture)!}
          alt={me.name}
          width={32}
          height={32}
          className="size-8 rounded object-cover"
        />
      ) : (
        <span className="grid size-8 place-items-center rounded bg-brand font-bold">
          {me.name[0]?.toUpperCase()}
        </span>
      )}
    </div>
  );
}
