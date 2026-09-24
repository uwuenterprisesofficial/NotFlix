import Link from "next/link";
import { apiOrNull } from "@/lib/api";
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
  const me = await currentUser();

  return (
    <header className="fixed inset-x-0 top-0 z-50 bg-gradient-to-b from-black/90 to-transparent">
      <nav className="mx-auto flex h-16 items-center gap-8 px-4 md:px-12">
        <Link href="/" className="text-2xl font-black tracking-tight text-brand md:text-3xl">
          NOTFLIX
        </Link>
        <div className="hidden gap-5 text-sm text-neutral-200 sm:flex">
          <Link href="/" className="hover:text-white">
            Home
          </Link>
          {me && (
            <Link href="/#my-list" className="hover:text-white">
              My List
            </Link>
          )}
        </div>
        <div className="ml-auto">
          {me ? (
            <UserMenu me={me} />
          ) : (
            // Plain anchor: this is a full-page redirect to MyAnimeList, not a client navigation.
            <a
              href="/api/auth/login"
              className="rounded bg-brand px-4 py-1.5 text-sm font-semibold hover:bg-brand-dark"
            >
              Sign in with MyAnimeList
            </a>
          )}
        </div>
      </nav>
    </header>
  );
}
