"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";
import { type Lang, saveLang } from "@/lib/i18n";
import { TIER_CLASS } from "@/lib/prediction";
import { useShowPredictedScore, useShowTierLabels } from "@/lib/preferences";
import type { Tier } from "@/lib/types";
import { useT } from "./I18nProvider";
import { LanguageFlag } from "./LanguageFlag";
import { PredictionBadge } from "./PredictionBadge";

const TIERS: Tier[] = ["must_watch", "recommended", "maybe", "skip", "avoid"];
const LANGUAGES: { lang: Lang; name: string; flag: "de-dub" | "en-dub" }[] = [
  { lang: "de", name: "Deutsch", flag: "de-dub" },
  { lang: "en", name: "English", flag: "en-dub" },
];

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
  const { t, lang } = useT();
  const router = useRouter();
  const [switching, startTransition] = useTransition();
  const [labels, setLabels] = useShowTierLabels();
  const [score, setScore] = useShowPredictedScore();

  function chooseLanguage(next: Lang) {
    saveLang(next);
    startTransition(() => router.refresh());
  }

  return (
    <div className="mt-8 space-y-8">
      <section>
        <h2 className="text-lg font-semibold">{t("settings.language")}</h2>
        <p className="mt-1 text-sm text-muted">{t("settings.languageInfo")}</p>
        <div role="radiogroup" aria-label={t("settings.language")} className="mt-3 flex gap-2">
          {LANGUAGES.map((l) => (
            <button
              key={l.lang}
              role="radio"
              aria-checked={l.lang === lang}
              disabled={switching}
              onClick={() => chooseLanguage(l.lang)}
              className={`flex items-center gap-2 rounded px-4 py-2 font-semibold ${l.lang === lang ? "bg-white text-black" : "bg-surface-raised hover:bg-neutral-700"}`}
            >
              <LanguageFlag language={l.flag} />
              {l.name}
            </button>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold">{t("settings.predictions")}</h2>
        <p className="mt-1 text-sm text-muted">{t("settings.predictionsInfo")}</p>
        <div className="mt-2 divide-y divide-white/10">
          <Toggle
            label={t("settings.labels")}
            description={t("settings.labelsInfo")}
            checked={labels === "on"}
            onChange={(on) => setLabels(on ? "on" : "off")}
          />
          <Toggle
            label={t("settings.score")}
            description={t("settings.scoreInfo")}
            checked={score === "on"}
            onChange={(on) => setScore(on ? "on" : "off")}
          />
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold">{t("settings.labelMeaning")}</h2>
        <p className="mt-1 text-sm text-muted">{t("settings.labelMeaningInfo")}</p>
        <ul className="mt-3 space-y-2 text-sm">
          {TIERS.map((tier) => (
            <li key={tier} className="flex items-center gap-3">
              <span
                className={`w-32 shrink-0 rounded px-2 py-1 text-center text-xs font-bold uppercase ${TIER_CLASS[tier]}`}
              >
                {t(`tier.${tier}`)}
              </span>
              <span className="text-neutral-300">{t(`tierInfo.${tier}`)}</span>
            </li>
          ))}
        </ul>
        <div className="mt-4 flex items-center gap-2 text-sm text-muted">
          {t("settings.preview")}
          <PredictionBadge prediction={{ score: 8.7, tier: "must_watch", reasons: [] }} force />
        </div>
      </section>
    </div>
  );
}
