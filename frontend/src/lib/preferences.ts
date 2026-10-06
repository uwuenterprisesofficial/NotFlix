import { useStoredValue } from "@/components/player/useStoredValue";

/** Show MUST WATCH / AVOID labels on posters (default on). */
export const useShowTierLabels = () => useStoredValue<"on" | "off">("notflix:tier-labels", "on");

/** Show the predicted score next to the label (default off). */
export const useShowPredictedScore = () =>
  useStoredValue<"on" | "off">("notflix:predicted-score", "off");

/** Which audio streams are picked first: a dub in the UI's language, or the original audio with
 * subtitles (default: dub). */
export type AudioPreference = "dub" | "sub";
export const useAudioPreference = () => useStoredValue<AudioPreference>("notflix:audio", "dub");

/** The home page's preview video: on or off (default on), and where it starts: at the beginning
 * of the episode, or at its opening when AniSkip knows where that is. */
export const useHeroPreview = () => useStoredValue<"on" | "off">("notflix:hero-preview", "on");
export const usePreviewStart = () =>
  useStoredValue<"start" | "opening">("notflix:preview-start", "start");
