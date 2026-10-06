"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import type { Progress } from "@/lib/types";
import { useT } from "./I18nProvider";

const SCORES = [10, 9, 8, 7, 6, 5, 4, 3, 2, 1];

/** The user's own score for a show, changed right here: saved to every linked list (MAL,
 * AniList). A show that isn't on the list yet goes there as completed. */
export function ScoreEditor({ animeId, progress }: { animeId: number; progress: Progress | null }) {
  const { t } = useT();
  const router = useRouter();
  const [score, setScore] = useState(progress?.score ?? 0);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  const [, startTransition] = useTransition();

  async function save(next: number) {
    const before = score;
    setScore(next);
    setState("saving");
    const res = await fetch(`/api/anime/${animeId}/score`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ score: next }),
    }).catch(() => null);
    if (!res?.ok) {
      setScore(before);
      setState("failed");
      return;
    }
    const saved: Progress = await res.json();
    setScore(saved.score);
    setState(saved.failed?.length ? "failed" : "saved");
    // The list status shown above may have changed (completed).
    startTransition(() => router.refresh());
  }

  return (
    <label className="inline-flex items-center gap-2 text-sm">
      <span className="text-muted">{t("score.yours")}</span>
      <select
        value={score}
        disabled={state === "saving"}
        onChange={(e) => save(Number(e.target.value))}
        className="rounded border border-white/20 bg-surface-raised px-2 py-1 font-semibold"
      >
        <option value={0}>{t("score.none")}</option>
        {SCORES.map((s) => (
          <option key={s} value={s}>
            ★ {s} · {t(`score.${s}` as "score.10")}
          </option>
        ))}
      </select>
      <span aria-live="polite" className="text-xs text-muted">
        {state === "saving"
          ? t("score.saving")
          : state === "saved"
            ? t("score.saved")
            : state === "failed"
              ? t("score.failed")
              : ""}
      </span>
    </label>
  );
}
