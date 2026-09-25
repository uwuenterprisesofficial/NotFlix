import type { Metadata } from "next";
import { SettingsForm } from "@/components/SettingsForm";
import { getT } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("nav.settings")} · NotFlix` };
}

export default async function SettingsPage() {
  const { t } = await getT();
  return (
    <div className="mx-auto max-w-2xl px-4 pt-24 pb-16">
      <h1 className="text-3xl font-black">{t("settings.title")}</h1>
      <p className="mt-1 text-sm text-muted">{t("settings.savedHere")}</p>
      <SettingsForm />
    </div>
  );
}
