"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useT } from "./I18nProvider";

const CHECK_EVERY_MS = 2500;

/** While the list is imported in the background (after the first sign-in): says so, and
 * shows the page with it once that's done. */
export function ImportingList({ empty }: { empty: boolean }) {
  const { t } = useT();
  const router = useRouter();

  useEffect(() => {
    const timer = setInterval(async () => {
      const me = await fetch("/api/me")
        .then((r) => (r.ok ? r.json() : null))
        .catch(() => null);
      if (me && !me.syncing) {
        clearInterval(timer);
        router.refresh();
      }
    }, CHECK_EVERY_MS);
    return () => clearInterval(timer);
  }, [router]);

  const spinner = (
    <span
      aria-hidden
      className="inline-block size-5 animate-spin rounded-full border-2 border-white/25 border-t-white"
    />
  );
  if (!empty) {
    return (
      <div role="status" className="mx-4 mb-4 flex items-center gap-3 text-sm text-muted md:mx-12">
        {spinner}
        {t("home.importingUpdate")}
      </div>
    );
  }
  return (
    <div
      role="status"
      className="mx-auto mt-24 max-w-lg rounded-lg bg-surface-raised p-8 text-center"
    >
      <div className="flex justify-center">{spinner}</div>
      <h2 className="mt-4 text-2xl font-bold">{t("home.importingTitle")}</h2>
      <p className="mt-3 text-muted">{t("home.importingBody")}</p>
    </div>
  );
}
