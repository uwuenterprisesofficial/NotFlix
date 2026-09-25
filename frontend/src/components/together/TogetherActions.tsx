"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { PENDING_INVITE_KEY } from "@/lib/together";
import { useT } from "../I18nProvider";

/** Create an invite link and copy it. */
export function InviteLink() {
  const { t } = useT();
  const [link, setLink] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [copied, setCopied] = useState(false);

  async function create() {
    setBusy(true);
    setFailed(false);
    const res = await fetch("/api/together/invites", { method: "POST" }).catch(() => null);
    if (res?.ok) {
      const { code } = await res.json();
      setLink(`${window.location.origin}/together/join/${code}`);
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
