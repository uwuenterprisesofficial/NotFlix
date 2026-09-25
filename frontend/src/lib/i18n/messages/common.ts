import type { Messages } from "../core";

const n = (count: number, one: string, many: string) => `${count} ${count === 1 ? one : many}`;

export const common = {
  // Navigation
  "nav.home": { en: "Home", de: "Start" },
  "nav.myList": { en: "My List", de: "Meine Liste" },
  "nav.stats": { en: "Statistics", de: "Statistiken" },
  "nav.search": { en: "Search", de: "Suche" },
  "nav.settings": { en: "Settings", de: "Einstellungen" },
  "nav.signIn": { en: "Sign in", de: "Anmelden" },
  "user.sync": { en: "Sync lists", de: "Listen synchronisieren" },
  "user.syncing": { en: "Syncing…", de: "Synchronisiere…" },
  "user.synced": {
    en: (v: { entries: number; recommendations: number }) =>
      `Synced ${n(v.entries, "show", "shows")} · ${n(v.recommendations, "recommendation", "recommendations")}`,
    de: (v: { entries: number; recommendations: number }) =>
      `${n(v.entries, "Serie", "Serien")} synchronisiert · ${n(v.recommendations, "Empfehlung", "Empfehlungen")}`,
  },
  "user.syncFailed": { en: "Sync failed", de: "Synchronisierung fehlgeschlagen" },
  "user.adding": {
    en: (v: { count: number; list: string }) =>
      `adding ${n(v.count, "entry", "entries")} to ${v.list}`,
    de: (v: { count: number; list: string }) =>
      `${n(v.count, "Eintrag wird", "Einträge werden")} zu ${v.list} hinzugefügt`,
  },
  "user.skipped": {
    en: (v: { count: number }) =>
      `${n(v.count, "AniList entry", "AniList entries")} without a MAL id skipped`,
    de: (v: { count: number }) =>
      `${n(v.count, "AniList-Eintrag", "AniList-Einträge")} ohne MAL-ID übersprungen`,
  },
  "list.mal": { en: "MyAnimeList", de: "MyAnimeList" },
  "list.anilist": { en: "AniList", de: "AniList" },

  // Sign-in
  "login.title": { en: "Sign in", de: "Anmelden" },
  "login.info": {
    en: "Use your MyAnimeList list, your AniList list, or both. With both, each list gets what only the other has on every sync, and your progress is saved to both.",
    de: "Nutze deine MyAnimeList-Liste, deine AniList-Liste oder beide. Mit beiden bekommt jede Liste bei jeder Synchronisierung, was nur die andere hat, und dein Fortschritt wird in beiden gespeichert.",
  },
  "login.mal": { en: "Sign in with MyAnimeList", de: "Mit MyAnimeList anmelden" },
  "login.anilist": { en: "Sign in with AniList", de: "Mit AniList anmelden" },
  "login.both": { en: "Sign in with both", de: "Mit beiden anmelden" },
  "login.bothInfo": {
    en: "MyAnimeList first, then AniList. MAL's show data is used; changes go to both.",
    de: "Erst MyAnimeList, dann AniList. MALs Seriendaten werden verwendet; Änderungen gehen an beide.",
  },
  "login.notConfigured": {
    en: "{list} isn't set up on this server ({vars} in .env).",
    de: "{list} ist auf diesem Server nicht eingerichtet ({vars} in .env).",
  },
  "login.failed": {
    en: "Signing in failed. Try again.",
    de: "Anmeldung fehlgeschlagen. Versuch es nochmal.",
  },

  // Accounts in Settings
  "accounts.title": { en: "Your lists", de: "Deine Listen" },
  "accounts.info": {
    en: "Linked lists are synced together: each gets what only the other has, show data comes from MyAnimeList, and progress is saved to all of them.",
    de: "Verknüpfte Listen werden gemeinsam synchronisiert: Jede bekommt, was nur die andere hat, Seriendaten kommen von MyAnimeList, und Fortschritt wird in allen gespeichert.",
  },
  "accounts.linked": { en: "Linked as {name}", de: "Verknüpft als {name}" },
  "accounts.notLinked": { en: "Not linked", de: "Nicht verknüpft" },
  "accounts.link": { en: "Link", de: "Verknüpfen" },
  "accounts.unlink": { en: "Remove", de: "Entfernen" },
  "accounts.unlinkConfirm": {
    en: "Remove {list}? Its entries stay on {list}; NotFlix just stops syncing it.",
    de: "{list} entfernen? Die Einträge bleiben auf {list}; NotFlix synchronisiert sie nur nicht mehr.",
  },
  "accounts.lastOne": { en: "Your only list", de: "Deine einzige Liste" },
  "accounts.writing": {
    en: "Adding to {list}: {done} of {total}",
    de: "Wird zu {list} hinzugefügt: {done} von {total}",
  },
  "accounts.signInFirst": {
    en: "Sign in to link your lists.",
    de: "Melde dich an, um deine Listen zu verknüpfen.",
  },
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
  "row.new-episodes": { en: "New Episodes", de: "Neue Folgen" },
  "row.calendar": { en: "Release calendar ›", de: "Veröffentlichungskalender ›" },
  "nav.calendar": { en: "Calendar", de: "Kalender" },
  "airing.episode": { en: "E{episode}", de: "F{episode}" },
  "airing.notAired": { en: "Not aired yet", de: "Noch nicht ausgestrahlt" },
  // The air time follows these (formatted in the browser, in the viewer's time zone).
  "airing.firstOn": { en: "episode 1 airs ", de: "Folge 1 erscheint am " },
  "airing.nextOn": { en: "Episode {episode} airs ", de: "Folge {episode} erscheint am " },
  "airing.notYetTitle": {
    en: "Episode {episode} hasn't aired yet",
    de: "Folge {episode} wurde noch nicht ausgestrahlt",
  },
  "airing.notYetInfo": {
    en: "There are no streams before it airs, so none are looked for.",
    de: "Vor der Ausstrahlung gibt es keine Streams, deshalb wird auch nicht danach gesucht.",
  },
  "airing.upcoming": { en: "Not aired yet", de: "Noch nicht erschienen" },
  "airing.back": { en: "‹ Back to the show", de: "‹ Zurück zur Serie" },

  // Calendar
  "calendar.title": { en: "Release calendar", de: "Veröffentlichungskalender" },
  "calendar.info": {
    en: "When new episodes air in Japan (times in your time zone). Streams usually follow within hours; German releases often later.",
    de: "Wann neue Folgen in Japan ausgestrahlt werden (Zeiten in deiner Zeitzone). Streams folgen meist nach ein paar Stunden, deutsche Fassungen oft später.",
  },
  "calendar.prev": { en: "‹ Previous week", de: "‹ Vorherige Woche" },
  "calendar.next": { en: "Next week ›", de: "Nächste Woche ›" },
  "calendar.thisWeek": { en: "This week", de: "Diese Woche" },
  "calendar.mine": { en: "Only my list", de: "Nur meine Liste" },
  "calendar.loading": { en: "Loading the schedule…", de: "Lade den Sendeplan…" },
  "calendar.updating": { en: "Updating the schedule…", de: "Sendeplan wird aktualisiert…" },
  "calendar.empty": { en: "Nothing airs", de: "Nichts läuft" },
  "calendar.failed": {
    en: "Couldn't load the schedule.",
    de: "Der Sendeplan konnte nicht geladen werden.",
  },
  "calendar.today": { en: "Today", de: "Heute" },
  "calendar.aired": { en: "aired", de: "erschienen" },
  "row.scrollLeft": { en: "Scroll left", de: "Nach links scrollen" },
  "row.scrollRight": { en: "Scroll right", de: "Nach rechts scrollen" },
  "reason.becauseYouLiked": {
    en: "Because you liked {title}",
    de: "Weil dir {title} gefallen hat",
  },
  "home.emptyTitle": { en: "Nothing here yet", de: "Noch nichts hier" },
  "home.emptyBody": {
    en: "Press “Sync lists” to import your list and build recommendations.",
    de: "Klicke auf „Listen synchronisieren“, um deine Liste zu importieren und Empfehlungen zu erstellen.",
  },
  "home.connectTitle": {
    en: "Connect MyAnimeList or AniList",
    de: "MyAnimeList oder AniList verbinden",
  },
  "home.connectBody": {
    en: "Create an API client at myanimelist.net/apiconfig (MAL_CLIENT_ID, MAL_CLIENT_SECRET) or anilist.co/settings/developer (ANILIST_CLIENT_ID, ANILIST_CLIENT_SECRET), put it in .env and restart the backend.",
    de: "Lege einen API-Client unter myanimelist.net/apiconfig (MAL_CLIENT_ID, MAL_CLIENT_SECRET) oder anilist.co/settings/developer (ANILIST_CLIENT_ID, ANILIST_CLIENT_SECRET) an, trage ihn in .env ein und starte das Backend neu.",
  },
  "home.signInBody": {
    en: "Sign in with MyAnimeList or AniList to see your list and personal recommendations.",
    de: "Melde dich mit MyAnimeList oder AniList an, um deine Liste und persönliche Empfehlungen zu sehen.",
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
    en: "The language of NotFlix, of synopses where one is available (German ones come from AniWorld or AnimeToast), and the stream language picked first: dub, then sub in this language, then dub, then sub in the other.",
    de: "Die Sprache von NotFlix, der Beschreibungen, wo es eine gibt (deutsche kommen von AniWorld oder AnimeToast), und die zuerst gewählte Stream-Sprache: Synchro, dann Untertitel in dieser Sprache, danach Synchro, dann Untertitel in der anderen.",
  },
  "settings.design": { en: "Design", de: "Design" },
  "settings.designInfo": { en: "How NotFlix looks.", de: "Wie NotFlix aussieht." },
  "design.standard": { en: "Standard", de: "Standard" },
  "design.standardInfo": {
    en: "Black and red, like the original.",
    de: "Schwarz und Rot, wie das Original.",
  },
  "design.communism": { en: "Communism", de: "Kommunismus" },
  "design.communismInfo": {
    en: "Red and gold, bold capitals, a star on top.",
    de: "Rot und Gold, fette Großbuchstaben, ein Stern obendrauf.",
  },
  "design.miku": { en: "Miku", de: "Miku" },
  "design.mikuInfo": {
    en: "Teal and pink, rounded letters, ♪.",
    de: "Türkis und Pink, runde Buchstaben, ♪.",
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
