import type { Tier } from "./types";

export const TIER_LABEL: Record<Tier, string> = {
  must_watch: "Must watch",
  recommended: "Recommended",
  maybe: "Maybe",
  skip: "Probably skip",
  avoid: "Avoid",
};

/** Badge colours: green for the tiers worth watching, grey in between, amber/red below. */
export const TIER_CLASS: Record<Tier, string> = {
  must_watch: "bg-emerald-500 text-black",
  recommended: "bg-green-800 text-green-50",
  maybe: "bg-neutral-700 text-neutral-100",
  skip: "bg-amber-800 text-amber-50",
  avoid: "bg-red-900 text-red-50",
};

export const TIER_DESCRIPTION: Record<Tier, string> = {
  must_watch: "Predicted among the best 15% of what you've watched",
  recommended: "Predicted better than most of what you've watched",
  maybe: "Predicted around your usual",
  skip: "Predicted below most of what you've watched",
  avoid: "Predicted among the worst 12% of what you've watched",
};
