import type { Metadata } from "next";
import { StatsView } from "@/components/stats/StatsView";
import { apiOrNull } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import type { Me } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("nav.stats")} · NotFlix` };
}

export default async function StatsPage() {
  const [me, { t }] = await Promise.all([apiOrNull<Me>("/me"), getT()]);
  if (!me || me.guest) {
    return (
      <div className="mx-auto mt-40 max-w-lg rounded-lg bg-surface-raised p-8 text-center">
        <h1 className="text-2xl font-bold">{t("nav.stats")}</h1>
        <p className="mt-3 text-muted">{me ? t("guest.stats") : t("stats.signIn")}</p>
      </div>
    );
  }
  return (
    <div className="mx-auto max-w-6xl px-4 pt-24 pb-16 md:px-12">
      <header className="mb-10">
        <h1 className="text-3xl font-black md:text-4xl">{t("stats.title")}</h1>
        <p className="mt-1 text-muted">{t("stats.subtitle")}</p>
      </header>
      {/* Loaded in the browser: the statistics are computed in the background. */}
      <StatsView />
    </div>
  );
}
