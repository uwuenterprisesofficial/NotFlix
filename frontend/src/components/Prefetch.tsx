"use client";

import { useEffect } from "react";
import type { PrefetchShow } from "@/lib/prefetch";

// A moment after the page shows: what's needed for it comes first.
const DELAY_MS = 3000;

/**
 * Hands a page's shows to the backend, which looks for their streams in the background while
 * nothing else is going on (see backend/app/services/prefetch.py). Renders nothing.
 */
export function Prefetch({ shows }: { shows: PrefetchShow[] }) {
  const key = shows.map((s) => `${s.id}:${s.episode}`).join(",");
  useEffect(() => {
    if (!key) return;
    const timer = setTimeout(() => {
      const body = key.split(",").map((s) => {
        const [id, episode] = s.split(":").map(Number);
        return { id, episode };
      });
      void fetch("/api/prefetch", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ shows: body }),
      }).catch(() => {});
    }, DELAY_MS);
    return () => clearTimeout(timer);
  }, [key]);
  return null;
}
