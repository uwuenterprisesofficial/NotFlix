import Link from "next/link";
import { apiOrNull } from "@/lib/api";
import { getT } from "@/lib/i18n/server";
import type { Me } from "@/lib/types";
import { UserMenu } from "./UserMenu";

async function currentUser(): Promise<Me | null> {
  try {
    return await apiOrNull<Me>("/me");
  } catch {
    return null; // Backend down: render signed-out; the page itself shows the error.
  }
}

export async function Navbar() {
  const [me, { t }] = await Promise.all([currentUser(), getT()]);

  return (
    <header className="fixed inset-x-0 top-0 z-50 bg-gradient-to-b from-black/90 to-transparent">
      <nav className="mx-auto flex h-16 items-center gap-8 px-4 md:px-12">
        <Link href="/" className="text-2xl font-black tracking-tight text-brand md:text-3xl">
          NOTFLIX
        </Link>
        <div className="hidden gap-5 text-sm text-neutral-200 sm:flex">
          <Link href="/" className="hover:text-white">
            {t("nav.home")}
          </Link>
          {me && (
            <Link href="/#my-list" className="hover:text-white">
              {t("nav.myList")}
            </Link>
          )}
          {me && (
            <Link href="/stats" className="hover:text-white">
              {t("nav.stats")}
            </Link>
          )}
        </div>
        <div className="ml-auto flex items-center gap-4">
          <Link
            href="/search"
            aria-label={t("nav.search")}
            title={t("nav.search")}
            className="text-xl hover:text-white"
          >
            <svg
              viewBox="0 0 24 24"
              className="size-5"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden
            >
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" strokeLinecap="round" />
            </svg>
          </Link>
          <Link
            href="/settings"
            aria-label={t("nav.settings")}
            title={t("nav.settings")}
            className="hover:text-white"
          >
            <svg
              viewBox="0 0 24 24"
              className="size-5"
              fill="none"
              stroke="currentColor"
              strokeWidth={2}
              aria-hidden
            >
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1Z" />
            </svg>
          </Link>
          {me ? (
            <UserMenu me={me} />
          ) : (
            <Link
              href="/login"
              className="rounded bg-brand px-4 py-1.5 text-sm font-semibold hover:bg-brand-dark"
            >
              {t("nav.signIn")}
            </Link>
          )}
        </div>
      </nav>
    </header>
  );
}
