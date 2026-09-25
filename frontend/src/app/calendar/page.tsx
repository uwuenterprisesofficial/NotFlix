import type { Metadata } from "next";
import { CalendarView } from "@/components/CalendarView";
import { getT } from "@/lib/i18n/server";

export async function generateMetadata(): Promise<Metadata> {
  const { t } = await getT();
  return { title: `${t("nav.calendar")} · NotFlix` };
}

export default async function CalendarPage() {
  const { t } = await getT();
  return (
    <div className="px-4 pt-24 pb-16 md:px-12">
      <h1 className="text-3xl font-black">{t("calendar.title")}</h1>
      <p className="mt-1 max-w-3xl text-sm text-muted">{t("calendar.info")}</p>
      {/* In the browser: days and times are in the viewer's time zone. */}
      <CalendarView />
    </div>
  );
}
