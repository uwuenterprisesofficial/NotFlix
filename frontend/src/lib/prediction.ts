import type { Tier } from "./types";

/** Badge colours: green for the tiers worth watching, grey in between, amber/red below. */
export const TIER_CLASS: Record<Tier, string> = {
  must_watch: "bg-emerald-500 text-black",
  recommended: "bg-green-800 text-green-50",
  maybe: "bg-neutral-700 text-neutral-100",
  skip: "bg-amber-800 text-amber-50",
  avoid: "bg-red-900 text-red-50",
};
