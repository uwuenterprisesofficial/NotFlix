"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

const EVERY_MS = 3000;
const AT_MOST = 20;

/** Shows the page again every few seconds (at most a minute) while the server is still
 * fetching part of it; gone once the page comes back complete. */
export function RefreshWhilePending() {
  const router = useRouter();
  useEffect(() => {
    let left = AT_MOST;
    const timer = setInterval(() => {
      if (--left <= 0) clearInterval(timer);
      router.refresh();
    }, EVERY_MS);
    return () => clearInterval(timer);
  }, [router]);
  return null;
}
