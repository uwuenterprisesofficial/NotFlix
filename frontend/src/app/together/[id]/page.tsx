import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AnimeRow } from "@/components/AnimeRow";
import { Avatar } from "@/components/together/Avatar";
import { Disconnect } from "@/components/together/TogetherActions";
import { apiOrNull } from "@/lib/api";
import { genreName, type T } from "@/lib/i18n";
import { getT } from "@/lib/i18n/server";
import { watchHref } from "@/lib/together";
import type { Connection, Row, Together } from "@/lib/types";

export async function generateMetadata({ params }: PageProps<"/together/[id]">): Promise<Metadata> {
  const { id } = await params;
  const { t } = await getT();
  const data = /^\d+$/.test(id) ? await apiOrNull<Together>(`/together/${id}`) : null;
  const title = data ? t("together.youAnd", { name: data.partner.name }) : t("together.title");
  return { title: `${title} · NotFlix` };
}

function rowTitle(t: T, row: Row, data: Together): string {
  switch (row.id) {
    case "show_to_partner":
      return t("together.row.showTo", { name: data.partner.name });
    case "show_to_me":
      return t("together.row.showTo", { name: data.me.name });
    case "continue":
    case "together":
    case "planned":
    case "both_loved":
      return t(`together.row.${row.id}`);
    default:
      return row.title;
  }
}

/** A 0-1 agreement as a bar. */
function Meter({ label, value }: { label: string; value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  return (
    <div>
      <div className="flex justify-between text-xs text-muted">
        <span>{label}</span>
        <span>{pct}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded bg-white/15">
        <div className="h-full bg-brand" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default async function ConnectionPage({ params }: PageProps<"/together/[id]">) {
  const { id } = await params;
  if (!/^\d+$/.test(id)) notFound();
  const [{ t, lang }, data, connections] = await Promise.all([
    getT(),
    apiOrNull<Together>(`/together/${id}`),
    apiOrNull<Connection[]>("/together"),
  ]);
  if (!data) notFound();
  const connection = connections?.find((c) => c.id === data.id);
  const watching = connection?.partner_watching;
  const compat = data.compatibility;
  const names = { me: t("together.you"), partner: data.partner.name };
  const rows = data.rows.map((row) => ({ ...row, title: rowTitle(t, row, data) }));
  if (compat.disagreements.length) {
    rows.push({ id: "disagree", title: t("together.disagree"), items: compat.disagreements });
  }

  return (
    <div className="pt-24 pb-16">
      <header className="mx-auto flex max-w-6xl flex-wrap items-start gap-8 px-4 md:px-12">
        <div className="flex items-center gap-3">
          <div className="flex -space-x-3">
            <Avatar person={data.me} size={56} />
            <Avatar person={data.partner} size={56} />
          </div>
          <div>
            <h1 className="text-3xl font-black md:text-4xl">
              {t("together.youAnd", { name: data.partner.name })}
            </h1>
            {compat.shared > 0 && (
              <p className="text-sm text-muted">
                {t("together.sharedShows", { n: compat.shared })}
              </p>
            )}
          </div>
        </div>

        <div className="min-w-64 flex-1 rounded-lg bg-surface-raised p-4 md:max-w-md">
          {compat.score === null ? (
            <p className="text-sm text-muted">{t("together.notEnough")}</p>
          ) : (
            <>
              <p className="flex items-baseline gap-2">
                <span className="text-4xl font-black text-brand">{compat.score}%</span>
                <span className="text-sm text-muted">{t("together.tasteMatch")}</span>
              </p>
              <div className="mt-3 space-y-2">
                {compat.correlation !== null && (
                  <Meter
                    label={t("together.scoreAgreement")}
                    value={(compat.correlation + 1) / 2}
                  />
                )}
                {compat.genre_similarity !== null && (
                  <Meter
                    label={t("together.genreAgreement")}
                    value={(compat.genre_similarity + 1) / 2}
                  />
                )}
              </div>
              {compat.shared_genres.length > 0 && (
                <p className="mt-3 flex flex-wrap items-center gap-1.5 text-xs">
                  <span className="text-muted">{t("together.sharedGenres")}:</span>
                  {compat.shared_genres.map((g) => (
                    <span key={g} className="rounded bg-white/10 px-2 py-0.5">
                      {genreName(lang, g)}
                    </span>
                  ))}
                </p>
              )}
            </>
          )}
        </div>
      </header>

      {watching && (
        <div className="mx-auto mt-6 flex max-w-6xl px-4 md:px-12">
          <Link
            href={watchHref(watching, data.id)}
            className="flex items-center gap-3 rounded-lg bg-white px-4 py-2 font-semibold text-black"
          >
            <span aria-hidden className="size-2 rounded-full bg-green-500" />
            {t("together.toast", {
              name: data.partner.name,
              title: watching.title ?? "?",
              episode: watching.episode,
            })}
            <span className="rounded bg-black px-2 py-0.5 text-sm text-white">
              ▶ {t("together.join")}
            </span>
          </Link>
        </div>
      )}

      <div className="mt-8 space-y-6">
        {rows.length === 0 ? (
          <p className="mx-auto max-w-6xl px-4 text-muted md:px-12">{t("together.nothing")}</p>
        ) : (
          rows.map((row) => <AnimeRow key={row.id} row={row} pairNames={names} />)
        )}
      </div>

      <div className="mx-auto mt-12 max-w-6xl px-4 md:px-12">
        <Disconnect id={data.id} name={data.partner.name} />
      </div>
    </div>
  );
}
