import type { Messages } from "../core";

const n = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

export const common = {
  // Navigation
  "nav.home": { en: "Home", de: "Start" },
  "nav.myList": { en: "My List", de: "Meine Liste" },
  "nav.stats": { en: "Statistics", de: "Statistiken" },
  "nav.search": { en: "Search", de: "Suche" },
  "nav.settings": { en: "Settings", de: "Einstellungen" },
  "nav.signIn": { en: "Sign in with MyAnimeList", de: "Mit MyAnimeList anmelden" },
  "user.sync": { en: "Sync MAL", de: "MAL synchronisieren" },
  "user.syncing": { en: "Syncing…", de: "Synchronisiere…" },
  "user.synced": {
    en: (v: { entries: number; recommendations: number }) =>
      `Synced ${n(v.entries, "show", "shows")} · ${n(v.recommendations, "recommendation", "recommendations")}`,
    de: (v: { entries: number; recommendations: number }) =>
      `${n(v.entries, "Serie", "Serien")} synchronisiert · ${n(v.recommendations, "Empfehlung", "Empfehlungen")}`,
  },
  "user.syncFailed": { en: "Sync failed", de: "Synchronisierung fehlgeschlagen" },
  "user.neverSynced": { en: "Never synced", de: "Noch nie synchronisiert" },
  "user.lastSynced": { en: "Last synced {when}", de: "Zuletzt synchronisiert: {when}" },
  "user.lastSyncedShort": { en: "Last synced", de: "Zuletzt synchronisiert" },
  "user.signOut": { en: "Sign out", de: "Abmelden" },

  // Home
  "row.continue": { en: "Continue Watching", de: "Weiterschauen" },
  "row.recommended": { en: "Recommended for You", de: "Empfehlungen für dich" },
  "row.my-list": { en: "My List", de: "Meine Liste" },
  "row.watch-again": { en: "Watch Again", de: "Nochmal ansehen" },
  "row.airing": { en: "Top Airing", de: "Aktuell beliebt" },
  "row.bypopularity": { en: "Most Popular", de: "Am beliebtesten" },
  "row.upcoming": { en: "Coming Soon", de: "Demnächst" },
  "row.scrollLeft": { en: "Scroll left", de: "Nach links scrollen" },
  "row.scrollRight": { en: "Scroll right", de: "Nach rechts scrollen" },
  "reason.becauseYouLiked": {
    en: "Because you liked {title}",
    de: "Weil dir {title} gefallen hat",
  },
  "home.emptyTitle": { en: "Nothing here yet", de: "Noch nichts hier" },
  "home.emptyBody": {
    en: "Press “Sync MAL” to import your MyAnimeList list and build recommendations.",
    de: "Klicke auf „MAL synchronisieren“, um deine MyAnimeList-Liste zu importieren und Empfehlungen zu erstellen.",
  },
  "home.connectTitle": { en: "Connect MyAnimeList", de: "MyAnimeList verbinden" },
  "home.connectBody": {
    en: "Create an API client at myanimelist.net/apiconfig, then set MAL_CLIENT_ID and MAL_CLIENT_SECRET in .env and restart the backend.",
    de: "Lege unter myanimelist.net/apiconfig einen API-Client an, trage MAL_CLIENT_ID und MAL_CLIENT_SECRET in .env ein und starte das Backend neu.",
  },
  "home.signInBody": {
    en: "Sign in with MyAnimeList to see your list and personal recommendations.",
    de: "Melde dich mit MyAnimeList an, um deine Liste und persönliche Empfehlungen zu sehen.",
  },

  // Hero / cards
  "hero.play": { en: "Play", de: "Abspielen" },
  "hero.resume": { en: "Resume E{episode}", de: "Weiter mit F{episode}" },
  "hero.moreInfo": { en: "More Info", de: "Mehr Infos" },
  "anime.episodes": {
    en: (v: { count: number }) => n(v.count, "episode", "episodes"),
    de: (v: { count: number }) => n(v.count, "Folge", "Folgen"),
  },

  // Errors
  "error.title": { en: "Something went wrong", de: "Etwas ist schiefgelaufen" },
  "error.body": {
    en: "Couldn’t load this page. Is the NotFlix API running?",
    de: "Die Seite konnte nicht geladen werden. Läuft die NotFlix-API?",
  },
  "error.id": { en: "Error ID: {id}", de: "Fehler-ID: {id}" },
  "error.retry": { en: "Try again", de: "Erneut versuchen" },

  // Predictions
  "tier.must_watch": { en: "Must watch", de: "Pflicht" },
  "tier.recommended": { en: "Recommended", de: "Empfohlen" },
  "tier.maybe": { en: "Maybe", de: "Vielleicht" },
  "tier.skip": { en: "Probably skip", de: "Eher nicht" },
  "tier.avoid": { en: "Avoid", de: "Meiden" },
  "tierInfo.must_watch": {
    en: "Predicted among the best 15% of what you've watched",
    de: "Voraussichtlich unter den besten 15 % von dem, was du gesehen hast",
  },
  "tierInfo.recommended": {
    en: "Predicted better than most of what you've watched",
    de: "Voraussichtlich besser als das meiste, was du gesehen hast",
  },
  "tierInfo.maybe": {
    en: "Predicted around your usual",
    de: "Voraussichtlich so gut wie üblich für dich",
  },
  "tierInfo.skip": {
    en: "Predicted below most of what you've watched",
    de: "Voraussichtlich schlechter als das meiste, was du gesehen hast",
  },
  "tierInfo.avoid": {
    en: "Predicted among the worst 12% of what you've watched",
    de: "Voraussichtlich unter den schlechtesten 12 % von dem, was du gesehen hast",
  },
  "prediction.predicted": { en: "predicted {score}", de: "Prognose {score}" },
  "prediction.yourScore": { en: "Your predicted score", de: "Deine vorhergesagte Wertung" },
  "feature.mal": { en: "MAL score", de: "MAL-Wertung" },
  "feature.popularity": { en: "Popularity", de: "Beliebtheit" },
  "feature.era": { en: "{decade}s", de: "{decade}er" },

  // Stream languages
  "lang.de-dub": { en: "German Dub", de: "Deutsch (Synchro)" },
  "lang.de-sub": { en: "German Sub", de: "Deutsch (Untertitel)" },
  "lang.en-sub": { en: "English Sub", de: "Englisch (Untertitel)" },
  "lang.en-dub": { en: "English Dub", de: "Englisch (Synchro)" },
  "lang.unknown": { en: "Other", de: "Sonstige" },
  "langShort.de-dub": { en: "DE", de: "DE" },
  "langShort.de-sub": { en: "DE Sub", de: "DE UT" },
  "langShort.en-sub": { en: "EN Sub", de: "EN UT" },
  "langShort.en-dub": { en: "EN", de: "EN" },
  "langShort.unknown": { en: "?", de: "?" },

  // Settings
  "settings.title": { en: "Settings", de: "Einstellungen" },
  "settings.savedHere": { en: "Saved in this browser.", de: "In diesem Browser gespeichert." },
  "settings.language": { en: "Language", de: "Sprache" },
  "settings.languageInfo": {
    en: "The language of NotFlix, of synopses where one is available (German ones come from AniWorld), and the stream language picked first: dub, then sub in this language, then dub, then sub in the other.",
    de: "Die Sprache von NotFlix, der Beschreibungen, wo es eine gibt (deutsche kommen von AniWorld), und die zuerst gewählte Stream-Sprache: Synchro, dann Untertitel in dieser Sprache, danach Synchro, dann Untertitel in der anderen.",
  },
  "settings.predictions": { en: "Predictions", de: "Prognosen" },
  "settings.predictionsInfo": {
    en: "Predicted from your MyAnimeList scores (genres, themes, demographics, studios, source, era and MAL's own score). Shows you have scored or dropped aren't labelled.",
    de: "Vorhergesagt aus deinen MyAnimeList-Wertungen (Genres, Themen, Zielgruppen, Studios, Vorlage, Jahrzehnt und MALs eigener Wertung). Serien, die du bewertet oder abgebrochen hast, bekommen kein Label.",
  },
  "settings.labels": { en: "Show labels on posters", de: "Labels auf Postern zeigen" },
  "settings.labelsInfo": {
    en: "MUST WATCH, RECOMMENDED, MAYBE, PROBABLY SKIP or AVOID in the corner of each poster.",
    de: "PFLICHT, EMPFOHLEN, VIELLEICHT, EHER NICHT oder MEIDEN in der Ecke jedes Posters.",
  },
  "settings.score": { en: "Show the predicted score", de: "Vorhergesagte Wertung zeigen" },
  "settings.scoreInfo": {
    en: "Your predicted score (1–10) next to the label.",
    de: "Deine vorhergesagte Wertung (1–10) neben dem Label.",
  },
  "settings.labelMeaning": { en: "What the labels mean", de: "Was die Labels bedeuten" },
  "settings.labelMeaningInfo": {
    en: "Labels compare a show with what you've already watched, so they adapt to how you score.",
    de: "Labels vergleichen eine Serie mit dem, was du schon gesehen hast – sie passen sich also daran an, wie du wertest.",
  },
  "settings.preview": { en: "Preview:", de: "Vorschau:" },
} satisfies Messages;
