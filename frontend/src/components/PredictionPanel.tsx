"use client";

import { featureName, formatNumber } from "@/lib/i18n";
import type { Prediction } from "@/lib/types";
import { useT } from "./I18nProvider";
import { PredictionBadge } from "./PredictionBadge";

/** "Predicted for you" with what moved the prediction, on a show's detail page. */
export function PredictionPanel({ prediction }: { prediction: Prediction }) {
  const { t, lang } = useT();
  return (
    <div className="mt-5 max-w-xl rounded-md bg-surface-raised p-4">
      <div className="flex flex-wrap items-center gap-3">
        <PredictionBadge prediction={prediction} size="md" force />
        <span className="text-sm">
          {t("prediction.yourScore")}{" "}
          <strong className="text-lg">{formatNumber(lang, prediction.score, 1)}</strong>
        </span>
      </div>
      <p className="mt-1 text-xs text-muted">{t(`tierInfo.${prediction.tier}`)}.</p>
      {prediction.reasons.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2 text-xs">
          {prediction.reasons.map((r) => (
            <li key={r.key} className="rounded-full border border-white/15 px-2.5 py-1">
              <span aria-hidden className={r.points >= 0 ? "text-green-400" : "text-red-400"}>
                {r.points >= 0 ? "▲" : "▼"}
              </span>{" "}
              {featureName(lang, r.key, r.name)}{" "}
              <span className="text-muted">
                {r.points >= 0 ? "+" : "−"}
                {formatNumber(lang, Math.abs(r.points), 1)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
