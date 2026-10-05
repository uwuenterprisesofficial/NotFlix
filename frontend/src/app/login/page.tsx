import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { ServerSettings } from "@/components/desktop/ServerSettings";
import { api, apiOrNull } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import type { Me } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("login.title")} · NotFlix` };
}

type Providers = {
  mal: boolean;
  anilist: boolean;
  /** The redirect URLs to register at each provider. */
  redirects?: { mal: string; anilist: string };
};

const FAILURES = ["denied", "expired", "token", "client"] as const;

// Plain anchors: these are full-page redirects to MyAnimeList/AniList, not client navigations.
export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  // The backend may be unreachable (in the desktop app: not chosen yet, or wrong): the page
  // still shows, with the server settings.
  const [{ t }, me, providers, params] = await Promise.all([
    getT(),
    apiOrNull<Me>("/me").catch(() => null),
    api<Providers>("/auth/providers").catch(() => null),
    searchParams,
  ]);
  // A guest signs in here to use their own list (keeping their Watch Together connections).
  if (me && !me.guest) redirect("/settings");

  const option = (href: string, label: string, enabled: boolean, note?: string) => (
    <div>
      <a
        href={enabled ? href : undefined}
        aria-disabled={!enabled}
        className={`block rounded px-5 py-3 text-center font-semibold ${enabled ? "bg-brand hover:bg-brand-dark" : "cursor-not-allowed bg-surface-raised text-muted"}`}
      >
        {label}
      </a>
      {note && <p className="mt-1.5 text-xs text-muted">{note}</p>}
    </div>
  );

  /** Why signing in failed, as far as known: the reason comes from the backend's callback (or,
   * for "client", from the desktop app, which sees the provider's error page). */
  function failure() {
    const provider =
      params.provider === "anilist" ? "anilist" : params.provider === "mal" ? "mal" : null;
    const reason = FAILURES.find((r) => r === params.reason);
    const list = provider === "anilist" ? "AniList" : "MyAnimeList";
    const redirect = provider && providers?.redirects?.[provider];
    return (
      <div className="mt-4 text-sm text-red-400">
        <p>{provider && reason ? t(`login.failed.${reason}`, { list }) : t("login.failed")}</p>
        {redirect && (reason === "client" || reason === "token") && (
          <p className="mt-2 text-muted">
            {t("login.failed.redirect", { list })}{" "}
            <code className="break-all text-neutral-200">{redirect}</code>
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md px-4 pt-32 pb-16">
      <h1 className="text-3xl font-black">{t("login.title")}</h1>
      <p className="mt-2 text-muted">{t("login.info")}</p>
      {params.login === "failed" && failure()}
      {me?.guest && <p className="mt-4 text-sm">{t("guest.note")}</p>}
      {providers ? (
        <div className="mt-8 space-y-4">
        {option(
          "/api/auth/login?provider=mal",
          t("login.mal"),
          providers.mal,
          providers.mal
            ? undefined
            : t("login.notConfigured", {
                list: "MyAnimeList",
                vars: "MAL_CLIENT_ID, MAL_CLIENT_SECRET",
              }),
        )}
        {option(
          "/api/auth/login?provider=anilist",
          t("login.anilist"),
          providers.anilist,
          providers.anilist
            ? undefined
            : t("login.notConfigured", {
                list: "AniList",
                vars: "ANILIST_CLIENT_ID, ANILIST_CLIENT_SECRET",
              }),
        )}
        {providers.mal &&
          providers.anilist &&
          option(
            "/api/auth/login?provider=mal&then=anilist",
            t("login.both"),
            true,
            t("login.bothInfo"),
          )}
        </div>
      ) : (
        <p className="mt-8 text-red-400">{t("error.body")}</p>
      )}
      <ServerSettings unreachable={!providers} />
    </div>
  );
}
