import type { Messages } from "../core";

const eps = (list: number[], lang: "en" | "de") =>
  `${lang === "de" ? (list.length === 1 ? "Folge" : "Folgen") : list.length === 1 ? "episode" : "episodes"} ${list.join(", ")}`;

export const analysis = {
  "analysis.title": { en: "Intro & outro detection", de: "Intro- & Outro-Erkennung" },
  "analysis.info": {
    en: "The first time, two episodes are compared to find the opening and ending they share, and both are saved as fingerprints. Later episodes are just searched for those. The timestamps drive auto-skip. Only local files and direct streams can be analysed, not embedded players.",
    de: "Beim ersten Mal werden zwei Folgen verglichen, um ihr gemeinsames Opening und Ending zu finden; beide werden als Fingerabdruck gespeichert. Spätere Folgen werden nur noch danach durchsucht. Die Zeiten steuern das automatische Überspringen. Nur lokale Dateien und direkte Streams lassen sich analysieren, keine eingebetteten Player.",
  },
  "analysis.checking": {
    en: "Checking which episodes are available…",
    de: "Prüfe, welche Folgen verfügbar sind…",
  },
  "analysis.needsTwo": {
    en: (v: { label: string; found: number }) =>
      `Needs at least two episodes in ${v.label}; ${v.found === 1 ? "only one was" : "none were"} found. Pick another language in the episode list.`,
    de: (v: { label: string; found: number }) =>
      `Braucht mindestens zwei Folgen in ${v.label}; ${v.found === 1 ? "nur eine wurde" : "keine wurde"} gefunden. Wähle in der Folgenliste eine andere Sprache.`,
  },
  "analysis.pickRange": {
    en: "Pick a range with at least two {label} episodes.",
    de: "Wähle einen Bereich mit mindestens zwei Folgen in {label}.",
  },
  "analysis.hint": {
    en: (v: { episodes: number[]; label: string; compare: boolean }) => {
      const one = v.episodes.length === 1;
      return `Analyses ${eps(v.episodes, "en")} using ${one ? "its" : "their"} direct ${v.label} stream${one ? "" : "s"}${v.compare ? ", comparing episodes" : ""}, and replaces ${one ? "its" : "their"} earlier times (not ones entered by hand).`;
    },
    de: (v: { episodes: number[]; label: string; compare: boolean }) =>
      `Analysiert ${eps(v.episodes, "de")} über ${v.episodes.length === 1 ? "ihren" : "ihre"} direkten Stream (${v.label})${v.compare ? " per Folgenvergleich" : ""} und ersetzt frühere Zeiten (nicht die von Hand eingetragenen).`,
  },
  "analysis.startFailed": {
    en: "Could not start analysis ({status})",
    de: "Analyse konnte nicht gestartet werden ({status})",
  },
  "analysis.episodes": { en: "Episodes", de: "Folgen" },
  "analysis.to": { en: "to", de: "bis" },
  "analysis.analysing": { en: "Analysing…", de: "Analysiere…" },
  "analysis.analyse": { en: "Analyse", de: "Analysieren" },
  "analysis.compare": {
    en: "Compare episodes instead of searching for the saved fingerprints",
    de: "Folgen vergleichen statt nach den gespeicherten Fingerabdrücken zu suchen",
  },
  "analysis.job": {
    en: (v: { retry: boolean; episodes: number[] }) =>
      `${v.retry ? "Retry of" : "Job for"} ${eps(v.episodes, "en")}`,
    de: (v: { retry: boolean; episodes: number[] }) =>
      `${v.retry ? "Wiederholung für" : "Auftrag für"} ${eps(v.episodes, "de")}`,
  },
  "jobStatus.queued": { en: "queued", de: "wartet" },
  "jobStatus.running": { en: "running", de: "läuft" },
  "jobStatus.done": { en: "done", de: "fertig" },
  "jobStatus.failed": { en: "failed", de: "fehlgeschlagen" },
  "analysis.notFound": { en: "{label} not found", de: "{label} nicht gefunden" },
  "analysis.fromAniSkip": {
    en: "From AniSkip (crowd-sourced), until the detection finds this episode's exact times",
    de: "Von AniSkip (Community-Daten), bis die Erkennung die genauen Zeiten dieser Folge findet",
  },
  "analysis.manual": { en: "Entered manually", de: "Von Hand eingetragen" },
  "analysis.results": { en: "Results", de: "Ergebnisse" },
  "analysis.savedFingerprints": {
    en: "Saved fingerprints, searched for in new episodes:",
    de: "Gespeicherte Fingerabdrücke, nach denen neue Folgen durchsucht werden:",
  },
  "analysis.fromEpisode": {
    en: "{kind} from episode {episode} ({duration})",
    de: "{kind} aus Folge {episode} ({duration})",
  },
  "analysis.confirmRemove": {
    en: "Remove this fingerprint? Later analyses compare episodes again.",
    de: "Diesen Fingerabdruck entfernen? Spätere Analysen vergleichen dann wieder Folgen.",
  },
  "analysis.removeLabel": {
    en: "Remove the {kind} fingerprint",
    de: "{kind}-Fingerabdruck entfernen",
  },
  "analysis.removeTitle": {
    en: "Remove (e.g. if it's wrong)",
    de: "Entfernen (z. B. wenn er falsch ist)",
  },
  "analysis.runningJob": {
    en: (v: { running: boolean; episodes: number[] }) =>
      `${v.running ? "Analysing" : "Waiting to analyse"} ${eps(v.episodes, "en")}…`,
    de: (v: { running: boolean; episodes: number[] }) =>
      `${v.running ? "Analysiere" : "Wartet auf Analyse:"} ${eps(v.episodes, "de")}…`,
  },
  "analysis.stopLabel": {
    en: (v: { episodes: number[] }) => `Stop analysing ${eps(v.episodes, "en")}`,
    de: (v: { episodes: number[] }) => `Analyse von ${eps(v.episodes, "de")} stoppen`,
  },
  "analysis.stopTitle": {
    en: "Stop (it's marked as failed)",
    de: "Stoppen (wird als fehlgeschlagen markiert)",
  },
  "analysis.episodeLabel": { en: "Episode {episode}:", de: "Folge {episode}:" },
  "analysis.nothingFound": { en: "no intro or outro found", de: "kein Intro oder Outro gefunden" },
  "analysis.retryTitle": {
    en: "Download the episode again and recalculate its times",
    de: "Folge neu herunterladen und die Zeiten neu berechnen",
  },
  "analysis.retry": { en: "↻ Retry", de: "↻ Wiederholen" },
} satisfies Messages;
