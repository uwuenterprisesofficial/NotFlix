"use client";

import { type FormEvent, useEffect, useState } from "react";
import { type BackendError, useDesktop } from "@/lib/desktop";
import { useT } from "../I18nProvider";

/**
 * The desktop app's backend address and API key (only shown in the desktop app). Saving checks
 * that a NotFlix backend answers there and takes the key; the app then restarts its local
 * server with them and reloads.
 */
const FIELD =
  "mt-1 block w-full rounded bg-neutral-800 px-3 py-2 text-sm ring-1 ring-white/10 outline-none focus:ring-white/40";

export function ServerSettings({ unreachable = false }: { unreachable?: boolean }) {
  const { t } = useT();
  const desktop = useDesktop();
  const [current, setCurrent] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [key, setKey] = useState("");
  const [hasKey, setHasKey] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<BackendError | null>(null);

  useEffect(() => {
    void desktop?.backend().then((saved) => {
      setCurrent(saved.url);
      setHasKey(saved.hasKey);
      setUrl((typed) => typed || saved.url || "");
    });
  }, [desktop]);

  if (!desktop) return null;

  async function save(e: FormEvent) {
    e.preventDefault();
    if (!desktop) return;
    setBusy(true);
    setError(null);
    const result = await desktop.setBackend(url.trim(), key.trim());
    // On success the app reloads; until then it says so.
    if (!result.ok) {
      setError(result.error);
      setBusy(false);
    }
  }

  return (
    <section id="server" className="mt-10 rounded-lg bg-surface-raised p-5">
      <h2 className="text-lg font-semibold">{t("server.title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("server.info")}</p>
      {unreachable && (
        <p className="mt-3 text-sm text-red-400">
          {current ? t("server.unreachable", { url: current }) : t("server.missing")}
        </p>
      )}
      <form onSubmit={save} className="mt-4 space-y-3">
        <label className="block">
          <span className="text-sm font-semibold">{t("server.address")}</span>
          <input
            type="url"
            name="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://notflix.example.com/api"
            className={FIELD}
          />
        </label>
        <label className="block">
          <span className="text-sm font-semibold">{t("server.key")}</span>
          <input
            type="password"
            name="key"
            autoComplete="off"
            required={!hasKey}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={hasKey ? t("server.keySaved") : "API_KEY"}
            className={FIELD}
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded bg-brand px-4 py-2 text-sm font-semibold hover:bg-brand-dark disabled:opacity-60"
        >
          {busy ? t("server.checking") : t("server.connect")}
        </button>
      </form>
      {error && <p className="mt-2 text-sm text-red-400">{t(`server.error.${error}`)}</p>}
      <p className="mt-3 text-xs text-muted">{t("server.hint")}</p>
    </section>
  );
}
