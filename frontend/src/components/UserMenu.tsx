"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore, useTransition } from "react";
import type { Me } from "@/lib/types";

const noop = () => () => {};

export function UserMenu({ me }: { me: Me }) {
  // The server doesn't know the viewer's locale or timezone, so the local sync time is only
  // rendered after hydration.
  const hydrated = useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
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
      const { entries, recommendations } = await res.json();
      setMessage(`Synced ${entries} shows · ${recommendations} recommendations`);
      startTransition(() => router.refresh());
    } else {
      setMessage("Sync failed");
    }
  }

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    startTransition(() => router.refresh());
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      {message && <span className="hidden text-muted md:inline">{message}</span>}
      <button
        onClick={sync}
        disabled={syncing}
        className="rounded border border-white/30 px-3 py-1 hover:bg-white/10 disabled:opacity-50"
        title={
          !me.last_synced_at
            ? "Never synced"
            : hydrated
              ? `Last synced ${new Date(me.last_synced_at).toLocaleString()}`
              : "Last synced"
        }
      >
        {syncing ? "Syncing…" : "Sync MAL"}
      </button>
      <button onClick={logout} className="text-muted hover:text-white">
        Sign out
      </button>
      {me.picture ? (
        <Image
          src={me.picture}
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
