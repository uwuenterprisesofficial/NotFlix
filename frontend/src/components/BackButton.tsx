"use client";

import { usePathname, useRouter } from "next/navigation";
import { useT } from "./I18nProvider";

/** "‹" in the top bar: back to the previous page (home when this tab opened right here). */
export function BackButton() {
  const { t } = useT();
  const router = useRouter();
  const pathname = usePathname();
  if (pathname === "/") return null;
  return (
    <button
      // A tab opened right on this page has nothing to go back to.
      onClick={() => (window.history.length > 1 ? router.back() : router.push("/"))}
      aria-label={t("nav.back")}
      title={t("nav.back")}
      className="-mr-4 grid size-8 place-items-center rounded-full text-2xl leading-none text-neutral-200 hover:bg-white/10 hover:text-white"
    >
      ‹
    </button>
  );
}
