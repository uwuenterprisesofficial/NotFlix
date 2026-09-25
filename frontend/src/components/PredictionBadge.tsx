"use client";

import { TIER_CLASS, TIER_DESCRIPTION, TIER_LABEL } from "@/lib/prediction";
import { useShowPredictedScore, useShowTierLabels } from "@/lib/preferences";
import type { Prediction } from "@/lib/types";

/** The viewer's predicted verdict on a show, as set up in Settings. */
export function PredictionBadge({
  prediction,
  size = "sm",
  force = false,
}: {
  prediction: Prediction | null;
  size?: "sm" | "md";
  /** Show the label even when poster labels are turned off (e.g. on the detail page). */
  force?: boolean;
}) {
  const [labels] = useShowTierLabels();
  const [score] = useShowPredictedScore();
  if (!prediction || (labels === "off" && !force && score === "off")) return null;
  const showLabel = labels === "on" || force;

  return (
    <span
      title={`${TIER_DESCRIPTION[prediction.tier]} · predicted ${prediction.score.toFixed(1)}`}
      className={`inline-flex items-center gap-1 rounded font-bold tracking-wide uppercase shadow ${TIER_CLASS[prediction.tier]} ${size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-xs"}`}
    >
      {showLabel && TIER_LABEL[prediction.tier]}
      {score === "on" && (
        <span className={showLabel ? "border-l border-current/40 pl-1" : ""}>
          {prediction.score.toFixed(1)}
        </span>
      )}
    </span>
  );
}
