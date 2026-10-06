"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useDesktop } from "@/lib/desktop";
import { PENDING_INVITE_KEY } from "@/lib/together";
import { useT } from "../I18nProvider";

/** Where others open links: the desktop app's own server is only on this PC, so its links point
 * to the web app (the backend's FRONTEND_URL). */
async function publicOrigin(desktop: boolean): Promise<string> {
  if (desktop) {
    const providers = await fetch("/api/auth/providers")
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null);
    if (providers?.public_url) return String(providers.public_url).replace(/\/+$/, "");
  }
  return window.location.origin;
}

/** Create an invite link and copy it. */
export function InviteLink() {
  const { t } = useT();
  const [link, setLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);
  const desktop = useDesktop();

  async function create() {
    setBusy(true);
    setFailed(false);
    const res = await fetch("/api/together/invites", { method: "POST" }).catch(() => null);
    if (res?.ok) {
      const { code } = await res.json();
      setLink(`${await publicOrigin(!!desktop)}/together/join/${code}`);
    } else {
      setFailed(true);
    }
    setBusy(false);
  }

  async function copy() {
    if (!link) return;
    await navigator.clipboard?.writeText(link).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-lg bg-surface-raised p-4">
      <button
        onClick={create}
        disabled={busy}
        className="rounded bg-brand px-4 py-2 font-semibold hover:bg-brand-dark disabled:opacity-60"
      >
        {busy ? t("together.creating") : `＋ ${t("together.invite")}`}
      </button>
      {failed && <p className="mt-2 text-sm text-red-400">{t("together.inviteFailed")}</p>}
      {link && (
        <div className="mt-4">
          <p className="text-sm text-muted">{t("together.inviteInfo")}</p>
          <div className="mt-2 flex gap-2">
            <input
              readOnly
              value={link}
              onFocus={(e) => e.target.select()}
              aria-label={t("together.invite")}
              className="min-w-0 flex-1 rounded bg-black/40 px-3 py-2 font-mono text-sm"
            />
            <button onClick={copy} className="rounded bg-white px-4 py-2 font-semibold text-black">
              {copied ? `✓ ${t("together.copied")}` : t("together.copy")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export function AcceptInvite({ code, name }: { code: string; name: string }) {
  const { t } = useT();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function accept() {
    setBusy(true);
    setFailed(false);
    const res = await fetch(`/api/together/invites/${code}/accept`, { method: "POST" }).catch(
      () => null,
    );
    if (res?.ok) {
      const { id } = await res.json();
      router.push(`/together/${id}`);
      router.refresh();
      return;
    }
    setFailed(true);
    setBusy(false);
  }

  return (
    <div>
      <button
        onClick={accept}
        disabled={busy}
        className="rounded bg-brand px-5 py-2.5 font-semibold hover:bg-brand-dark disabled:opacity-60"
      >
        {busy ? t("together.connecting") : t("together.connect", { name })}
      </button>
      {failed && <p className="mt-2 text-sm text-red-400">{t("together.connectFailed")}</p>}
    </div>
  );
}

/** Accept an invite without an account: just a name. */
export function JoinAsGuest({ code }: { code: string }) {
  const { t } = useT();
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function join(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    setFailed(false);
    const res = await fetch(`/api/together/invites/${code}/guest`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    }).catch(() => null);
    if (res?.ok) {
      try {
        localStorage.removeItem(PENDING_INVITE_KEY); // taken up as a guest instead
      } catch {}
      const { id } = await res.json();
      router.push(`/together/${id}`);
      router.refresh();
      return;
    }
    setFailed(true);
    setBusy(false);
  }

  return (
    <form onSubmit={join} className="flex flex-wrap gap-2">
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        maxLength={40}
        required
        placeholder={t("together.guestName")}
        aria-label={t("together.guestName")}
        className="min-w-0 flex-1 rounded bg-black/40 px-3 py-2"
      />
      <button
        type="submit"
        disabled={busy || !name.trim()}
        className="rounded bg-white px-5 py-2 font-semibold text-black disabled:opacity-60"
      >
        {busy ? t("together.connecting") : t("together.guestJoin")}
      </button>
      {failed && <p className="w-full text-sm text-red-400">{t("together.guestFailed")}</p>}
    </form>
  );
}

/** Opened signed out: remember the invite, so it's taken up after signing in. */
export function RememberInvite({ code }: { code: string }) {
  useEffect(() => {
    try {
      localStorage.setItem(PENDING_INVITE_KEY, code);
    } catch {}
  }, [code]);
  return null;
}

export function Disconnect({ id, name }: { id: number; name: string }) {
  const { t } = useT();
  const router = useRouter();
  return (
    <button
      onClick={async () => {
        if (!window.confirm(t("together.disconnectConfirm", { name }))) return;
        const res = await fetch(`/api/together/${id}`, { method: "DELETE" }).catch(() => null);
        if (res?.ok) {
          router.push("/together");
          router.refresh();
        }
      }}
      className="text-sm text-muted hover:text-white"
    >
      {t("together.disconnect")}
    </button>
  );
}

/** Your friend code (whoever enters it is connected with you), and connecting by someone's. */
export function FriendCode() {
  const { t } = useT();
  const router = useRouter();
  const [code, setCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [entered, setEntered] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/together/code")
      .then((r) => (r.ok ? r.json() : null))
      .then(
        (body) => body && setCode(body.code),
        () => {},
      );
  }, []);

  async function copy() {
    if (!code) return;
    await navigator.clipboard?.writeText(code).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function renew() {
    if (!window.confirm(t("together.newCodeConfirm"))) return;
    const res = await fetch("/api/together/code", { method: "POST" }).catch(() => null);
    if (res?.ok) setCode((await res.json()).code);
  }

  async function connect(e: React.FormEvent) {
    e.preventDefault();
    if (!entered.trim()) return;
    setBusy(true);
    setError(null);
    const res = await fetch("/api/together/connect", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code: entered.trim() }),
    }).catch(() => null);
    setBusy(false);
    if (res?.ok) {
      setEntered("");
      router.refresh();
      return;
    }
    setError(
      res?.status === 409
        ? t("together.ownCode")
        : res?.status === 404
          ? t("together.unknownCode")
          : t("together.connectFailedShort"),
    );
  }

  return (
    <div className="grid gap-4 rounded-lg bg-surface-raised p-4 sm:grid-cols-2">
      <div>
        <p className="text-sm text-muted">{t("together.yourCode")}</p>
        <div className="mt-1 flex items-center gap-2">
          <span className="font-mono text-2xl font-bold tracking-widest">
            {code ?? "····-····"}
          </span>
          <button
            onClick={copy}
            disabled={!code}
            className="rounded bg-white/10 px-2 py-1 text-sm hover:bg-white/20"
          >
            {copied ? `✓ ${t("together.copied")}` : t("together.copy")}
          </button>
          <button
            onClick={renew}
            title={t("together.newCode")}
            aria-label={t("together.newCode")}
            className="px-1 text-muted hover:text-white"
          >
            ↻
          </button>
        </div>
        <p className="mt-1 text-xs text-muted">{t("together.codeInfo")}</p>
      </div>
      <form onSubmit={connect}>
        <label htmlFor="friend-code" className="text-sm text-muted">
          {t("together.addByCode")}
        </label>
        <div className="mt-1 flex gap-2">
          <input
            id="friend-code"
            value={entered}
            onChange={(e) => setEntered(e.target.value.toUpperCase())}
            placeholder="ABCD-EF23"
            maxLength={20}
            autoComplete="off"
            className="min-w-0 flex-1 rounded bg-black/40 px-3 py-2 font-mono tracking-widest"
          />
          <button
            type="submit"
            disabled={busy || !entered.trim()}
            className="rounded bg-brand px-4 py-2 font-semibold hover:bg-brand-dark disabled:opacity-60"
          >
            {busy ? t("together.connecting") : t("together.add")}
          </button>
        </div>
        {error && <p className="mt-1 text-sm text-red-400">{error}</p>}
      </form>
    </div>
  );
}
