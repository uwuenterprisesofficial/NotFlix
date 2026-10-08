"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { changesSince, type ChangelogEntry, shortVersion } from "@/lib/changelog";
import { type UpdateStatus, useDesktop } from "@/lib/desktop";
import { ChangelogEntries } from "../ChangelogEntries";
import { useT } from "../I18nProvider";

/**
 * The desktop app only: the changelog when a new version is opened for the first time, and
 * "Restart to update" once an update has been downloaded in the background.
 */
export function DesktopUpdates() {
  const desktop = useDesktop();
  if (!desktop) return null;
  return (
    <>
      <WhatsNew />
      <UpdateReady />
    </>
  );
}

function WhatsNew() {
  const { t } = useT();
  const desktop = useDesktop();
  const [entries, setEntries] = useState<ChangelogEntry[] | null>(null);

  useEffect(() => {
    void desktop?.version?.().then((v) => {
      if (!v?.isNew) return;
      const changes = changesSince(v.previous, v.version);
      if (changes.length) setEntries(changes);
      else void desktop.changelogSeen?.(); // nothing written down for it
    });
  }, [desktop]);

  if (!entries) return null;
  const close = () => {
    setEntries(null);
    void desktop?.changelogSeen?.();
  };
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="whats-new"
      className="fixed inset-0 z-[60] grid place-items-center bg-black/70 p-4 backdrop-blur-sm"
      onKeyDown={(e) => e.key === "Escape" && close()}
    >
      <div className="flex max-h-[85vh] w-full max-w-xl flex-col rounded-xl bg-surface-raised shadow-2xl ring-1 ring-white/10">
        <header className="border-b border-white/10 px-6 pt-5 pb-4">
          <p className="text-sm font-semibold tracking-wide text-brand uppercase">
            {t("changelog.updated", { version: shortVersion(entries[0].version) })}
          </p>
          <h1 id="whats-new" className="mt-1 text-2xl font-black">
            {t("changelog.whatsNew")}
          </h1>
        </header>
        <div className="overflow-y-auto px-6 py-5">
          <ChangelogEntries entries={entries} />
        </div>
        <footer className="flex items-center justify-between gap-3 border-t border-white/10 px-6 py-4">
          <Link href="/changelog" onClick={close} className="text-sm text-muted hover:text-white">
            {t("changelog.all")}
          </Link>
          <button
            autoFocus
            onClick={close}
            className="rounded bg-white px-5 py-2 font-semibold text-black hover:bg-white/80"
          >
            {t("changelog.continue")}
          </button>
        </footer>
      </div>
    </div>
  );
}

function UpdateReady() {
  const { t } = useT();
  const desktop = useDesktop();
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [later, setLater] = useState<string | null>(null);

  useEffect(() => {
    if (!desktop) return;
    void desktop.updateStatus?.().then((s) => s && setStatus(s));
    return desktop.onUpdateStatus?.(setStatus);
  }, [desktop]);

  if (status?.state !== "ready" || !status.version || later === status.version) return null;
  return (
    <div
      role="status"
      className="fixed right-4 bottom-4 z-50 flex max-w-sm items-center gap-3 rounded-lg bg-surface-raised p-3 pl-4 text-sm shadow-2xl ring-1 ring-white/10"
    >
      <span aria-hidden className="text-lg">
        ⬆
      </span>
      <span className="flex-1">
        <span className="block font-semibold">
          {t("update.ready", { version: shortVersion(status.version) })}
        </span>
        <span className="text-muted">{t("update.restartInfo")}</span>
      </span>
      <button
        onClick={() => void desktop?.installUpdate?.()}
        className="rounded bg-white px-3 py-1 font-semibold whitespace-nowrap text-black"
      >
        {t("update.restart")}
      </button>
      <button
        onClick={() => setLater(status.version)}
        className="px-1 text-muted hover:text-white"
        aria-label={t("update.later")}
        title={t("update.later")}
      >
        ✕
      </button>
    </div>
  );
}

/** Settings: the version, and checking for an update by hand. */
export function AppVersion() {
  const { t } = useT();
  const desktop = useDesktop();
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);

  useEffect(() => {
    if (!desktop) return;
    void desktop.updateStatus?.().then((s) => s && setStatus(s));
    return desktop.onUpdateStatus?.((s) => setStatus((old) => ({ ...s, current: old?.current })));
  }, [desktop]);

  if (!desktop || !status) return null;
  const text: Partial<Record<UpdateStatus["state"], string>> = {
    unsupported: t("update.unsupported"),
    noServer: t("update.noServer"),
    checking: t("update.checking"),
    upToDate: t("update.upToDate"),
    downloading: t("update.downloading", {
      version: shortVersion(status.version ?? "?"),
      progress: status.progress ?? 0,
    }),
    ready: t("update.ready", { version: shortVersion(status.version ?? "?") }),
    error: t("update.failed"),
  };
  return (
    <section className="mt-10 rounded-lg bg-surface-raised p-5">
      <h2 className="text-lg font-semibold">{t("update.title")}</h2>
      <p className="mt-1 text-sm">
        {t("update.current", { version: shortVersion(status.current ?? "?") })}
        {text[status.state] && <span className="text-muted"> · {text[status.state]}</span>}
      </p>
      {status.state === "error" && status.error && (
        <p className="mt-1 text-xs break-words text-red-400">{status.error}</p>
      )}
      <div className="mt-3 flex flex-wrap gap-2 text-sm">
        {status.state === "ready" ? (
          <button
            onClick={() => void desktop.installUpdate?.()}
            className="rounded bg-white px-4 py-2 font-semibold text-black"
          >
            {t("update.restart")}
          </button>
        ) : (
          <button
            disabled={checking || ["unsupported", "noServer", "downloading"].includes(status.state)}
            onClick={async () => {
              setChecking(true);
              const s = await desktop.checkForUpdates?.();
              if (s) setStatus(s);
              setChecking(false);
            }}
            className="rounded bg-white/10 px-4 py-2 font-semibold hover:bg-white/20 disabled:opacity-50"
          >
            {t("update.check")}
          </button>
        )}
        <Link href="/changelog" className="rounded px-4 py-2 text-muted hover:text-white">
          {t("changelog.all")}
        </Link>
      </div>
    </section>
  );
}
