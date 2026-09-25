"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";
import type { ListProvider, Me } from "@/lib/types";
import { useT } from "./I18nProvider";

const LISTS: { provider: ListProvider; name: string }[] = [
  { provider: "mal", name: "MyAnimeList" },
  { provider: "anilist", name: "AniList" },
];
const POLL_MS = 3000;

/** The linked lists (MyAnimeList, AniList): link another one, or remove one. */
export function AccountSettings({
  me,
  providers,
}: {
  me: Me | null;
  providers: Record<ListProvider, boolean>;
}) {
  const { t } = useT();
  const router = useRouter();
  const [, startTransition] = useTransition();
  const [writing, setWriting] = useState(me?.writing ?? null);

  // While entries are being added to the other list, show how far that is.
  const busy = !!writing;
  useEffect(() => {
    if (!busy) return;
    const timer = setInterval(async () => {
      const res = await fetch("/api/me").catch(() => null);
      if (res?.ok) setWriting(((await res.json()) as Me).writing);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [busy]);

  if (!me) return <p className="mt-2 text-sm text-muted">{t("accounts.signInFirst")}</p>;
  const linked = LISTS.filter((l) => me[l.provider]);

  async function unlink(provider: ListProvider, name: string) {
    if (!confirm(t("accounts.unlinkConfirm", { list: name }))) return;
    await fetch(`/api/auth/accounts/${provider}`, { method: "DELETE" });
    startTransition(() => router.refresh());
  }

  return (
    <ul className="mt-3 divide-y divide-white/10 rounded-lg bg-surface-raised">
      {LISTS.map(({ provider, name }) => {
        const account = me[provider];
        const progress = writing?.[provider];
        return (
          <li key={provider} className="flex flex-wrap items-center gap-3 px-4 py-3">
            <span className="w-28 font-semibold">{name}</span>
            <span className="flex-1 text-sm text-muted">
              {account
                ? t("accounts.linked", { name: account.name ?? "?" })
                : t("accounts.notLinked")}
              {progress && progress.total > 0 && progress.done < progress.total && (
                <span className="block text-xs">
                  {t("accounts.writing", {
                    list: name,
                    done: progress.done,
                    total: progress.total,
                  })}
                </span>
              )}
            </span>
            {account ? (
              linked.length > 1 ? (
                <button
                  onClick={() => unlink(provider, name)}
                  className="rounded px-3 py-1 text-sm text-muted hover:bg-white/10 hover:text-white"
                >
                  {t("accounts.unlink")}
                </button>
              ) : (
                <span className="text-xs text-muted">{t("accounts.lastOne")}</span>
              )
            ) : (
              // A full-page redirect to the provider's sign-in.
              <a
                href={
                  providers[provider] ? `/api/auth/login?provider=${provider}&link=true` : undefined
                }
                aria-disabled={!providers[provider]}
                className={`rounded px-3 py-1 text-sm font-semibold ${providers[provider] ? "bg-brand hover:bg-brand-dark" : "cursor-not-allowed bg-white/5 text-muted"}`}
              >
                {t("accounts.link")}
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}
