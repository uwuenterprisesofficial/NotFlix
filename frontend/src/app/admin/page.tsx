import type { Metadata } from "next";
import { AdminView } from "@/components/AdminView";
import { apiOrNull } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import type { Me } from "@/lib/types";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("admin.title")} · NotFlix` };
}

export default async function AdminPage() {
  const [{ t }, me] = await Promise.all([getT(), apiOrNull<Me>("/me")]);
  return (
    <div className="mx-auto max-w-6xl px-4 pt-24 pb-16">
      <h1 className="mb-4 text-3xl font-black">{t("admin.title")}</h1>
      {me?.admin ? <AdminView /> : <p className="text-muted">{t("admin.forbidden")}</p>}
    </div>
  );
}
