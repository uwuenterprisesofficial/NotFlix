import { useStoredValue } from "@/components/player/useStoredValue";

/** Show MUST WATCH / AVOID labels on posters (default on). */
export const useShowTierLabels = () => useStoredValue<"on" | "off">("notflix:tier-labels", "on");

/** Show the predicted score next to the label (default off). */
export const useShowPredictedScore = () =>
  useStoredValue<"on" | "off">("notflix:predicted-score", "off");
