"use client";

import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import {
  type BackendError,
  type BuiltInUpdate,
  type DesktopBackend,
  type DesktopBridge,
  useDesktop,
} from "@/lib/desktop";
import { useT } from "../I18nProvider";

const FIELD =
  "mt-1 block w-full rounded bg-neutral-800 px-3 py-2 text-sm ring-1 ring-white/10 outline-none focus:ring-white/40";
const BUTTON =
  "rounded bg-brand px-4 py-2 text-sm font-semibold hover:bg-brand-dark disabled:opacity-60";

/**
 * Where the desktop app's backend runs (only shown in the desktop app): the built-in server on
 * this PC (when the app has one), with its sign-in settings, or another server by its address
 * and API key, optionally with streams found and played on this PC (hybrid). Saving restarts
 * what runs and reloads the app.
 */
export function ServerSettings({ unreachable = false }: { unreachable?: boolean }) {
  const { t } = useT();
  const desktop = useDesktop();
  const [saved, setSaved] = useState<DesktopBackend | null>(null);
  const [mode, setMode] = useState<DesktopBackend["mode"] | null>(null);

  useEffect(() => {
    void desktop?.backend().then((value) => {
      setSaved(value);
      setMode((chosen) => chosen ?? value.mode);
    });
  }, [desktop]);

  if (!desktop || !saved || !mode) return null;
  const shown = saved.builtIn ? mode : "remote";

  return (
    <section id="server" className="mt-10 rounded-lg bg-surface-raised p-5">
      <h2 className="text-lg font-semibold">{t("server.title")}</h2>
      <p className="mt-1 text-sm text-muted">{t("server.info")}</p>
      {saved.builtIn && (
        <div role="radiogroup" className="mt-4 grid grid-cols-2 gap-2 text-sm">
          {(["builtin", "remote"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="radio"
              aria-checked={shown === m}
              onClick={() => setMode(m)}
              className={`rounded px-3 py-2 font-semibold ring-1 ${shown === m ? "bg-white text-black ring-white" : "ring-white/15 hover:ring-white/40"}`}
            >
              {t(m === "builtin" ? "server.builtIn" : "server.remote")}
            </button>
          ))}
        </div>
      )}
      {shown === "builtin" && saved.builtIn ? (
        <BuiltInForm desktop={desktop} saved={saved} />
      ) : (
        <RemoteForm desktop={desktop} saved={saved} unreachable={unreachable} />
      )}
    </section>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="text-sm font-semibold">{label}</span>
      {children}
    </label>
  );
}

function ErrorText({ error }: { error: BackendError | null }) {
  const { t } = useT();
  return error && <p className="mt-2 text-sm text-red-400">{t(`server.error.${error}`)}</p>;
}

function RemoteForm({
  desktop,
  saved,
  unreachable,
}: {
  desktop: DesktopBridge;
  saved: DesktopBackend;
  unreachable: boolean;
}) {
  const { t } = useT();
  const [url, setUrl] = useState(saved.url ?? "");
  const [key, setKey] = useState("");
  const builtIn = saved.builtIn;
  const [hybrid, setHybrid] = useState(saved.hybrid);
  const [aniworldVia, setAniworldVia] = useState(builtIn?.settings.aniworldVia ?? "aniscraper");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<BackendError | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const result = await desktop.setBackend(url.trim(), key.trim(), {
      hybrid: !!builtIn && hybrid,
      aniworldVia,
    });
    // On success the app reloads; until then it says so.
    if (!result.ok) {
      setError(result.error);
      setBusy(false);
    }
  }

  return (
    <>
      {unreachable && saved.mode === "remote" && (
        <p className="mt-3 text-sm text-red-400">
          {saved.url ? t("server.unreachable", { url: saved.url }) : t("server.missing")}
        </p>
      )}
      {saved.mode === "remote" && saved.hybrid && builtIn?.error && (
        <p className="mt-3 text-sm text-red-400">
          {t("server.hybridError", { error: builtIn.error })}
        </p>
      )}
      <form onSubmit={save} className="mt-4 space-y-3">
        <Field label={t("server.address")}>
          <input
            type="url"
            name="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://notflix.example.com/api"
            className={FIELD}
          />
        </Field>
        <Field label={t("server.key")}>
          <input
            type="password"
            name="key"
            autoComplete="off"
            required={!saved.hasKey}
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={saved.hasKey ? t("server.keySaved") : "API_KEY"}
            className={FIELD}
          />
        </Field>
        {builtIn && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              name="hybrid"
              checked={hybrid}
              onChange={(e) => setHybrid(e.target.checked)}
              className="mt-1"
            />
            <span>
              <span className="font-semibold">{t("server.hybrid")}</span>
              <span className="block text-xs text-muted">{t("server.hybridInfo")}</span>
            </span>
          </label>
        )}
        {builtIn?.serienStream && hybrid && (
          <Field label={t("server.aniworldVia")}>
            <select
              value={aniworldVia}
              onChange={(e) => setAniworldVia(e.target.value as typeof aniworldVia)}
              className={FIELD}
            >
              <option value="aniscraper">{t("server.viaAniScraper")}</option>
              <option value="serienstream">{t("server.viaSerienStream")}</option>
            </select>
          </Field>
        )}
        <button type="submit" disabled={busy} className={BUTTON}>
          {busy ? t("server.checking") : t("server.connect")}
        </button>
      </form>
      <ErrorText error={error} />
      <p className="mt-3 text-xs text-muted">{t("server.hint")}</p>
    </>
  );
}

function BuiltInForm({ desktop, saved }: { desktop: DesktopBridge; saved: DesktopBackend }) {
  const { t } = useT();
  const builtIn = saved.builtIn!;
  const [form, setForm] = useState<BuiltInUpdate>({
    malClientId: builtIn.settings.malClientId,
    malClientSecret: "",
    anilistClientId: builtIn.settings.anilistClientId,
    anilistClientSecret: "",
    aniworldVia: builtIn.settings.aniworldVia,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<BackendError | null>(null);
  const set = (key: keyof BuiltInUpdate) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));
  // Where the sign-ins come back to: what to register at MyAnimeList and AniList. (This form
  // only renders in the browser, once the app has answered.)
  const redirect = `http://localhost:${window.location.port}/api/auth`;

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const result = await desktop.setBuiltIn(form);
    if (!result.ok) {
      setError(result.error);
      setBusy(false);
    }
  }

  return (
    <>
      <p className="mt-3 text-sm text-muted">{t("server.builtInInfo")}</p>
      {saved.mode === "builtin" && builtIn.error && (
        <p className="mt-3 text-sm text-red-400">
          {t("server.builtInError", { error: builtIn.error })}
        </p>
      )}
      <form onSubmit={save} className="mt-4 space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("server.malClientId")}>
            <input value={form.malClientId} onChange={set("malClientId")} className={FIELD} />
          </Field>
          <Field label={t("server.malClientSecret")}>
            <input
              type="password"
              autoComplete="off"
              value={form.malClientSecret}
              onChange={set("malClientSecret")}
              placeholder={builtIn.settings.hasMalSecret ? t("server.keySaved") : ""}
              className={FIELD}
            />
          </Field>
          <Field label={t("server.anilistClientId")}>
            <input
              value={form.anilistClientId}
              onChange={set("anilistClientId")}
              className={FIELD}
            />
          </Field>
          <Field label={t("server.anilistClientSecret")}>
            <input
              type="password"
              autoComplete="off"
              value={form.anilistClientSecret}
              onChange={set("anilistClientSecret")}
              placeholder={builtIn.settings.hasAnilistSecret ? t("server.keySaved") : ""}
              className={FIELD}
            />
          </Field>
        </div>
        <p className="text-xs text-muted">
          {t("server.redirects")} <code className="text-neutral-200">{redirect}/callback</code>,{" "}
          <code className="text-neutral-200">{redirect}/anilist/callback</code>
        </p>
        {builtIn.serienStream && (
          <Field label={t("server.aniworldVia")}>
            <select value={form.aniworldVia} onChange={set("aniworldVia")} className={FIELD}>
              <option value="aniscraper">{t("server.viaAniScraper")}</option>
              <option value="serienstream">{t("server.viaSerienStream")}</option>
            </select>
          </Field>
        )}
        <div className="flex flex-wrap gap-2">
          <button type="submit" disabled={busy} className={BUTTON}>
            {busy ? t("server.restarting") : t("server.saveRestart")}
          </button>
          <button
            type="button"
            onClick={() => void desktop.openLogs()}
            className="rounded px-4 py-2 text-sm font-semibold ring-1 ring-white/15 hover:ring-white/40"
          >
            {t("server.logs")}
          </button>
        </div>
      </form>
      <ErrorText error={error} />
    </>
  );
}
