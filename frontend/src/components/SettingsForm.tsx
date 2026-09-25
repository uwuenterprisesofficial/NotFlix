"use client";

import { TIER_CLASS, TIER_DESCRIPTION, TIER_LABEL } from "@/lib/prediction";
import { useShowPredictedScore, useShowTierLabels } from "@/lib/preferences";
import type { Tier } from "@/lib/types";
import { PredictionBadge } from "./PredictionBadge";

const TIERS: Tier[] = ["must_watch", "recommended", "maybe", "skip", "avoid"];

function Toggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-6 py-4">
      <span>
        <span className="font-semibold">{label}</span>
        <span className="mt-0.5 block text-sm text-muted">{description}</span>
      </span>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="peer sr-only"
      />
      <span
        aria-hidden
        className="relative mt-1 h-6 w-11 shrink-0 rounded-full bg-neutral-600 transition-colors peer-checked:bg-brand peer-focus-visible:ring-2 peer-focus-visible:ring-white after:absolute after:top-0.5 after:left-0.5 after:size-5 after:rounded-full after:bg-white after:transition-transform peer-checked:after:translate-x-5"
      />
    </label>
  );
}

export function SettingsForm() {
  const [labels, setLabels] = useShowTierLabels();
  const [score, setScore] = useShowPredictedScore();

  return (
    <div className="mt-8 space-y-8">
      <section>
        <h2 className="text-lg font-semibold">Predictions</h2>
        <p className="mt-1 text-sm text-muted">
          Predicted from your MyAnimeList scores (genres, themes, demographics, studios, source, era
          and MAL&apos;s own score). Shows you have scored or dropped aren&apos;t labelled.
        </p>
        <div className="mt-2 divide-y divide-white/10">
          <Toggle
            label="Show labels on posters"
            description="MUST WATCH, RECOMMENDED, MAYBE, PROBABLY SKIP or AVOID in the corner of each poster."
            checked={labels === "on"}
            onChange={(on) => setLabels(on ? "on" : "off")}
          />
          <Toggle
            label="Show the predicted score"
            description="Your predicted score (1–10) next to the label."
            checked={score === "on"}
            onChange={(on) => setScore(on ? "on" : "off")}
          />
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold">What the labels mean</h2>
        <p className="mt-1 text-sm text-muted">
          Labels compare a show with what you&apos;ve already watched, so they adapt to how you
          score.
        </p>
        <ul className="mt-3 space-y-2 text-sm">
          {TIERS.map((tier) => (
            <li key={tier} className="flex items-center gap-3">
              <span
                className={`w-32 shrink-0 rounded px-2 py-1 text-center text-xs font-bold uppercase ${TIER_CLASS[tier]}`}
              >
                {TIER_LABEL[tier]}
              </span>
              <span className="text-neutral-300">{TIER_DESCRIPTION[tier]}</span>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex items-center gap-2 text-sm text-muted">
          Preview:
          <PredictionBadge prediction={{ score: 8.7, tier: "must_watch", reasons: [] }} force />
        </div>
      </section>
    </div>
  );
}
