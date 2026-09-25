import type { Metadata } from "next";
import Link from "next/link";
import { AccountSettings } from "@/components/AccountSettings";
import { SettingsForm } from "@/components/SettingsForm";
import { cookies } from "next/headers";
import { api, apiOrNull } from "@/lib/api";
import { DESIGN_COOKIE, isDesign } from "@/lib/design";
import type { Me } from "@/lib/types";
import { getT } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("nav.settings")} · NotFlix` };
}

export default async function SettingsPage() {
  const chosen = (await cookies()).get(DESIGN_COOKIE)?.value;
  const [{ t }, me, providers] = await Promise.all([
    getT(),
    apiOrNull<Me>("/me"),
    api<{ mal: boolean; anilist: boolean }>("/auth/providers"),
  ]);
  return (
    <div className="mx-auto max-w-2xl px-4 pt-24 pb-16">
      <h1 className="text-3xl font-black">{t("settings.title")}</h1>
      <p className="mt-1 text-sm text-muted">{t("settings.savedHere")}</p>
      <section className="mt-8">
        <h2 className="text-lg font-semibold">{t("accounts.title")}</h2>
        <p className="mt-1 text-sm text-muted">{t("accounts.info")}</p>
        <AccountSettings me={me} providers={providers} />
      </section>
      <SettingsForm design={isDesign(chosen) ? chosen : "standard"} />
      {me?.admin && (
        <section className="mt-10">
          <h2 className="text-lg font-semibold">{t("admin.title")}</h2>
          <p className="mt-1 text-sm text-muted">{t("admin.link")}</p>
          <Link
            href="/admin"
            className="mt-3 inline-block rounded bg-surface-raised px-4 py-2 text-sm font-semibold hover:bg-neutral-700"
          >
            {t("admin.open")} ›
          </Link>
        </section>
      )}
    </div>
  );
}
