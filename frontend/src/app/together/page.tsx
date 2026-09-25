import type { Metadata } from "next";
import Link from "next/link";
import { Avatar } from "@/components/together/Avatar";
import { InviteLink } from "@/components/together/TogetherActions";
import { api, apiOrNull } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import { watchHref } from "@/lib/together";
import type { Connection, Me } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("together.title")} · NotFlix` };
}

export default async function TogetherPage() {
  const [{ t }, me] = await Promise.all([getT(), apiOrNull<Me>("/me")]);
  if (!me) {
    return (
      <div className="mx-auto max-w-3xl px-4 pt-24 pb-16">
        <h1 className="text-3xl font-black">{t("together.title")}</h1>
        <p className="mt-3 text-muted">
          <Link href="/login" className="underline hover:text-white">
            {t("together.signIn")}
          </Link>
        </p>
      </div>
    );
  }
  const connections = await api<Connection[]>("/together");

  return (
    <div className="mx-auto max-w-3xl px-4 pt-24 pb-16">
      <h1 className="text-3xl font-black md:text-4xl">{t("together.title")}</h1>
      <p className="mt-1 text-muted">{t("together.subtitle")}</p>
      {me.guest && (
        <p className="mt-4 rounded bg-surface-raised p-3 text-sm">
          {t("guest.note")}{" "}
          <Link href="/login" className="underline hover:text-white">
            {t("guest.signIn")}
          </Link>
        </p>
      )}

      <div className="mt-8">
        <InviteLink />
      </div>

      {connections.length === 0 ? (
        <p className="mt-8 text-muted">{t("together.noConnectionsYet")}</p>
      ) : (
        <ul className="mt-8 space-y-3">
          {connections.map((c) => (
            <li
              key={c.id}
              className="flex flex-wrap items-center gap-4 rounded-lg bg-surface-raised p-4"
            >
              <Avatar person={c.partner} />
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 font-semibold">
                  {c.partner.name}
                  {c.partner_online && (
                    <span className="flex items-center gap-1 text-xs font-normal text-green-400">
                      <span aria-hidden className="size-2 rounded-full bg-green-400" />
                      {t("together.online")}
                    </span>
                  )}
                </p>
                <p className="text-sm text-muted">
                  {c.partner_watching
                    ? t("together.watchingNow", {
                        title: c.partner_watching.title ?? "?",
                        episode: c.partner_watching.episode,
                      })
                    : c.compatibility !== null
                      ? t("together.match", { score: c.compatibility })
                      : null}
                </p>
              </div>
              {c.partner_watching && (
                <Link
                  href={watchHref(c.partner_watching, c.id)}
                  prefetch={false}
                  className="rounded bg-white px-4 py-1.5 text-sm font-semibold text-black"
                >
                  ▶ {t("together.join")}
                </Link>
              )}
              <Link
                href={`/together/${c.id}`}
                // Each would compute that pair's recommendations: only when opened.
                prefetch={false}
                className="rounded bg-brand px-4 py-1.5 text-sm font-semibold hover:bg-brand-dark"
              >
                {t("together.open")}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
