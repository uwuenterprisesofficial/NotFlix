"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useRef, useState } from "react";
import { allowedImage } from "@/lib/images";
import type { Connection, Language, RoomStream } from "@/lib/types";
import { useT } from "../I18nProvider";
import type { useSources } from "../player/useSources";
import type { Party } from "./WatchParty";

type Sources = ReturnType<typeof useSources>;

export function streamOf(sources: Sources): RoomStream | null {
  if (!sources.active) return null;
  return {
    language: sources.language,
    provider: sources.active.provider,
    label: sources.active.label,
    server: sources.stream?.label ?? null,
  };
}

/**
 * Under the player: who you're watching with (and whether they're here), the partner's stream
 * when it's another one, and leaving. Without a room: a button to start one with a connection.
 */
export function TogetherBar({
  party,
  animeId,
  episode,
  sources,
  signedIn,
}: {
  party: Party | null;
  animeId: number;
  episode: number;
  sources: Sources;
  signedIn: boolean;
}) {
  if (!signedIn) return null;
  return party ? (
    <InRoom party={party} animeId={animeId} episode={episode} sources={sources} />
  ) : (
    <div className="mt-4 text-sm">
      <WatchTogetherMenu />
    </div>
  );
}

function InRoom({
  party,
  animeId,
  episode,
  sources,
}: {
  party: Party;
  animeId: number;
  episode: number;
  sources: Sources;
}) {
  const { t } = useT();
  const partner = party.partner;
  const name = partner?.name ?? "…";
  const theirs = party.members.find((m) => m.user_id !== party.me);
  const here = theirs && theirs.anime_id === animeId && theirs.episode === episode;
  const state = party.state;
  const matches = state && state.anime_id === animeId && state.episode === episode;

  // The partner plays another stream: offer theirs (their language first, then their source).
  const other = matches && state.stream && state.by !== party.me ? state.stream : null;
  const mine = streamOf(sources);
  const differs =
    other &&
    mine &&
    (other.language !== mine.language ||
      other.provider !== mine.provider ||
      other.label !== mine.label);
  const sameSource =
    other &&
    sources.candidates.find((o) => o.provider === other.provider && o.label === other.label);

  return (
    <div className="mt-4 flex flex-wrap items-center gap-3 rounded bg-surface-raised px-4 py-2 text-sm">
      <span className="flex items-center gap-2 font-semibold">
        {partner && allowedImage(partner.picture) ? (
          <Image
            src={allowedImage(partner.picture)!}
            alt=""
            width={22}
            height={22}
            className="rounded-full"
          />
        ) : (
          <span aria-hidden>👥</span>
        )}
        {t("together.watchingWith", { name })}
      </span>
      <span className={`flex items-center gap-1.5 ${here ? "text-green-400" : "text-muted"}`}>
        <span
          aria-hidden
          className={`inline-block size-2 rounded-full ${here ? "bg-green-400" : theirs ? "bg-amber-400" : "bg-neutral-500"}`}
        />
        {here
          ? t("together.here")
          : theirs
            ? t("together.elsewhere", { name })
            : t("together.notHere", { name })}
      </span>
      {party.offline && <span className="text-amber-400">{t("together.reconnecting")}</span>}
      {differs && (
        <span className="text-muted">
          {t("together.theirStream", {
            name,
            label: other.label ?? "?",
            language: other.language ? t(`lang.${other.language as Language}`) : "?",
          })}{" "}
          <button
            onClick={() =>
              other.language !== sources.language && other.language
                ? sources.setLanguage(other.language as Language)
                : sameSource && sources.choose(sameSource.id)
            }
            disabled={other.language === sources.language && !sameSource}
            className="underline hover:text-white disabled:no-underline disabled:opacity-60"
          >
            {t("together.useTheirs")}
          </button>
        </span>
      )}
      {sources.stream?.kind === "embed" && (
        <span className="text-amber-400">{t("together.embedNoSync")}</span>
      )}
      <Link href={party.leaveHref} className="ml-auto text-muted hover:text-white">
        {t("together.leave")}
      </Link>
    </div>
  );
}

/** Pick someone to watch with: opens `href` (a watch page), or this page, in their room. */
export function WatchTogetherMenu({ href, large = false }: { href?: string; large?: boolean }) {
  const { t } = useT();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const [open, setOpen] = useState(false);
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const loading = useRef(false);

  function toggle() {
    setOpen((o) => !o);
    if (connections || loading.current) return;
    loading.current = true;
    fetch("/api/together")
      .then((r) => (r.ok ? r.json() : []))
      .then(setConnections, () => setConnections([]));
  }

  function start(id: number) {
    if (href) {
      router.push(`${href}${href.includes("?") ? "&" : "?"}together=${id}`);
      return;
    }
    const params = new URLSearchParams(search.toString());
    params.set("together", String(id));
    router.replace(`${pathname}?${params}`);
  }

  return (
    <div className="relative">
      <button
        onClick={toggle}
        aria-expanded={open}
        className={
          large
            ? "inline-flex items-center gap-2 rounded bg-white/20 px-5 py-2 font-semibold backdrop-blur hover:bg-white/30"
            : "rounded bg-surface-raised px-3 py-1 hover:bg-neutral-700"
        }
      >
        👥 {t("together.watchTogether")}
      </button>
      {open && (
        <div className="absolute z-20 mt-1 min-w-56 rounded bg-surface-raised p-1 text-sm shadow-lg">
          {connections === null ? (
            <p className="px-3 py-2 text-muted">{t("together.loading")}</p>
          ) : connections.length === 0 ? (
            <p className="px-3 py-2 text-muted">
              {t("together.noConnections")}{" "}
              <Link href="/together" className="underline hover:text-white">
                {t("together.inviteSomeone")}
              </Link>
            </p>
          ) : (
            connections.map((c) => (
              <button
                key={c.id}
                onClick={() => start(c.id)}
                className="flex w-full items-center justify-between gap-3 rounded px-3 py-2 text-left hover:bg-white/10"
              >
                {t("together.withName", { name: c.partner.name })}
                {c.partner_online && (
                  <span aria-hidden className="size-2 rounded-full bg-green-400" />
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
