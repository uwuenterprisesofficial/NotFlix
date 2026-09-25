import type { Messages } from "../core";

export const detail = {
  "detail.resume": { en: "Resume episode {episode}", de: "Weiter mit Folge {episode}" },
  "detail.resumeAt": {
    en: "Resume episode {episode} at {time}",
    de: "Folge {episode} ab {time} fortsetzen",
  },
  "detail.play1": { en: "Play episode 1", de: "Folge 1 abspielen" },
  "detail.moreLikeThis": { en: "{category} · more like this", de: "{category} · mehr davon" },
  "detail.synopsisEnglish": {
    en: "",
    de: "Keine deutsche Beschreibung gefunden – hier die englische von MyAnimeList.",
  },
  "detail.synopsisLoading": { en: "", de: "Suche deutsche Beschreibung…" },
  "detail.moreOptions": { en: "More options", de: "Weitere Optionen" },
  "detail.moreOptionsInfo": {
    en: "AniWorld & AnimeToast pages, intro & outro detection",
    de: "AniWorld- & AnimeToast-Seiten, Intro- & Outro-Erkennung",
  },
  "category.genre": { en: "Genre", de: "Genre" },
  "category.theme": { en: "Theme", de: "Thema" },
  "category.demographic": { en: "Demographic", de: "Zielgruppe" },
  "category.explicit": { en: "Explicit", de: "Explizit" },
  "status.finished_airing": { en: "Finished airing", de: "Abgeschlossen" },
  "status.currently_airing": { en: "Currently airing", de: "Läuft gerade" },
  "status.not_yet_aired": { en: "Not yet aired", de: "Noch nicht ausgestrahlt" },
  "season.winter": { en: "Winter {year}", de: "Winter {year}" },
  "season.spring": { en: "Spring {year}", de: "Frühling {year}" },
  "season.summer": { en: "Summer {year}", de: "Sommer {year}" },
  "season.fall": { en: "Fall {year}", de: "Herbst {year}" },
  "list.watching": { en: "Watching", de: "Schaue ich" },
  "list.completed": { en: "Completed", de: "Abgeschlossen" },
  "list.on_hold": { en: "On hold", de: "Pausiert" },
  "list.dropped": { en: "Dropped", de: "Abgebrochen" },
  "list.plan_to_watch": { en: "Plan to watch", de: "Geplant" },

  // Episode list
  "episodes.title": { en: "Episodes", de: "Folgen" },
  "episodes.language": { en: "Language", de: "Sprache" },
  "episodes.refresh": { en: "↻ Refresh sources", de: "↻ Quellen aktualisieren" },
  "episodes.loadFailed": {
    en: "Couldn’t load episode availability.",
    de: "Verfügbarkeit der Folgen konnte nicht geladen werden.",
  },
  "episodes.looking": {
    en: "Looking for episodes on {providers}…",
    de: "Suche Folgen auf {providers}…",
  },
  "episodes.unreachable": {
    en: "{providers} couldn’t be reached; retrying later.",
    de: "{providers} nicht erreichbar; wird später erneut versucht.",
  },
  "episodes.withoutStream": {
    en: (v: { count: number }) =>
      `${v.count} episode${v.count === 1 ? "" : "s"} without any stream.`,
    de: (v: { count: number }) => `${v.count} ${v.count === 1 ? "Folge" : "Folgen"} ohne Stream.`,
  },
  "episodes.otherOnly": { en: "Other languages only", de: "Nur andere Sprachen" },
  "episodes.noStream": { en: "No stream", de: "Kein Stream" },
  "episodes.noStreamFound": {
    en: "No stream found for this episode",
    de: "Kein Stream für diese Folge gefunden",
  },
  "episodes.lookingStreams": { en: "Looking for streams…", de: "Suche Streams…" },
  "episodes.noStreamLabel": {
    en: "Episode {episode}: no stream",
    de: "Folge {episode}: kein Stream",
  },

  // Mappings
  "mapping.saved": {
    en: "Saved. Looking for German sources with this mapping…",
    de: "Gespeichert. Suche deutsche Quellen mit dieser Zuordnung…",
  },
  "mapping.savedToast": {
    en: "Saved. Looking for AnimeToast sources with these pages…",
    de: "Gespeichert. Suche AnimeToast-Quellen auf diesen Seiten…",
  },
  "mapping.slugHint": {
    en: "Use the slug from the AniWorld URL, e.g. one-piece.",
    de: "Verwende den Slug aus der AniWorld-URL, z. B. one-piece.",
  },
  "mapping.slugHintToast": {
    en: "Use the page slugs from the animetoast URLs, e.g. naruto-ger-dub, naruto-ger-sub.",
    de: "Verwende die Seiten-Slugs aus den animetoast-URLs, z. B. naruto-ger-dub, naruto-ger-sub.",
  },
  "mapping.saveFailed": { en: "Saving failed.", de: "Speichern fehlgeschlagen." },
  "mapping.reset": {
    en: "Reset. Detecting the series again…",
    de: "Zurückgesetzt. Serie wird neu erkannt…",
  },
  "mapping.resetToast": {
    en: "Reset. Searching animetoast again…",
    de: "Zurückgesetzt. Suche erneut auf animetoast…",
  },
  "mapping.manual": { en: "Set manually", de: "Manuell gesetzt" },
  "mapping.detected": { en: "Detected", de: "Erkannt" },
  "mapping.season": { en: "season {season}", de: "Staffel {season}" },
  "mapping.offset": { en: "episode offset {offset}", de: "Folgenversatz {offset}" },
  "mapping.notFound": {
    en: "Not found on {site} automatically.",
    de: "Auf {site} nicht automatisch gefunden.",
  },
  "mapping.notDetected": {
    en: "Not detected yet. It is looked up while the episode list loads.",
    de: "Noch nicht erkannt. Das passiert, während die Folgenliste lädt.",
  },
  "mapping.aniworldTitle": { en: "German sources (AniWorld)", de: "Deutsche Quellen (AniWorld)" },
  "mapping.toastTitle": { en: "AnimeToast pages", de: "AnimeToast-Seiten" },
  "mapping.toastInfo": {
    en: "animetoast has one page per season and language; list every language page of this season.",
    de: "animetoast hat eine Seite pro Staffel und Sprache; gib alle Sprachseiten dieser Staffel an.",
  },
  "mapping.seriesSlug": { en: "Series slug", de: "Serien-Slug" },
  "mapping.pageSlugs": { en: "Page slugs", de: "Seiten-Slugs" },
  "mapping.seasonLabel": { en: "Season", de: "Staffel" },
  "mapping.offsetLabel": { en: "Episode offset", de: "Folgenversatz" },
  "mapping.offsetInfo": {
    en: "Added to the episode number, for shows AniWorld numbers continuously",
    de: "Wird zur Folgennummer addiert, für Serien, die durchgehend nummeriert sind",
  },
  "mapping.save": { en: "Save", de: "Speichern" },
  "mapping.resetButton": { en: "Reset", de: "Zurücksetzen" },
} satisfies Messages;
