import { TIER_DESCRIPTION } from "@/lib/prediction";
import type { Prediction } from "@/lib/types";
import { PredictionBadge } from "./PredictionBadge";

/** "Predicted for you" with what moved the prediction, on a show's detail page. */
export function PredictionPanel({ prediction }: { prediction: Prediction }) {
  return (
    <div className="mt-5 max-w-xl rounded-md bg-surface-raised p-4">
      <div className="flex flex-wrap items-center gap-3">
        <PredictionBadge prediction={prediction} size="md" force />
        <span className="text-sm">
          Your predicted score <strong className="text-lg">{prediction.score.toFixed(1)}</strong>
        </span>
      </div>
      <p className="mt-1 text-xs text-muted">{TIER_DESCRIPTION[prediction.tier]}.</p>
      {prediction.reasons.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2 text-xs">
          {prediction.reasons.map((r) => (
            <li key={r.name} className="rounded-full border border-white/15 px-2.5 py-1">
              <span aria-hidden className={r.points >= 0 ? "text-green-400" : "text-red-400"}>
                {r.points >= 0 ? "▲" : "▼"}
              </span>{" "}
              {r.name}{" "}
              <span className="text-muted">
                {r.points >= 0 ? "+" : "−"}
                {Math.abs(r.points).toFixed(1)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
