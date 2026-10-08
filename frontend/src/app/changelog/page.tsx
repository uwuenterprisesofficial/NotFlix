import type { Metadata } from "next";
import { ChangelogEntries } from "@/components/ChangelogEntries";
import { CHANGELOG } from "@/lib/changelog";
import { getT } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("changelog.title")} · NotFlix` };
}

/** What's new in every version. */
export default async function ChangelogPage() {
  const { t } = await getT();
  return (
    <div className="mx-auto max-w-2xl px-4 pt-24 pb-16">
      <h1 className="mb-8 text-3xl font-black">{t("changelog.title")}</h1>
      <ChangelogEntries entries={CHANGELOG} />
    </div>
  );
}
