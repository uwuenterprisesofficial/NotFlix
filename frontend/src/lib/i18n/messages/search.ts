import type { Messages } from "../core";

export const search = {
  "search.title": { en: "Search", de: "Suche" },
  "search.placeholder": { en: "Search anime on MyAnimeList…", de: "Anime auf MyAnimeList suchen…" },
  "search.titleLabel": { en: "Title", de: "Titel" },
  "search.genre": { en: "Genre", de: "Genre" },
  "search.anyGenre": { en: "Any genre", de: "Alle Genres" },
  "search.groupGenre": { en: "Genres", de: "Genres" },
  "search.groupTheme": { en: "Themes", de: "Themen" },
  "search.groupDemographic": { en: "Demographics", de: "Zielgruppen" },
  "search.groupExplicit": { en: "Explicit genres", de: "Explizite Genres" },
  "search.order": { en: "Order", de: "Sortierung" },
  "search.orderScore": { en: "Top rated", de: "Am besten bewertet" },
  "search.orderPopularity": { en: "Most popular", de: "Am beliebtesten" },
  "search.orderNewest": { en: "Newest", de: "Neueste" },
  "search.orderForYou": { en: "Best for you", de: "Am besten für dich" },
  "search.bestMatch": { en: "Best match", de: "Beste Treffer" },
  "search.orderInfo": {
    en: "MAL's title search has its own order; this sorts the page",
    de: "MALs Titelsuche hat ihre eigene Reihenfolge; das sortiert nur diese Seite",
  },
  "search.submit": { en: "Search", de: "Suchen" },
  "search.intro": {
    en: "Search MyAnimeList by title, or pick a genre, theme or demographic to browse.",
    de: "Suche auf MyAnimeList nach Titel oder wähle ein Genre, Thema oder eine Zielgruppe zum Stöbern.",
  },
  "search.resultsFor": { en: "Results for “{q}”", de: "Ergebnisse für „{q}“" },
  "search.inGenre": { en: " in {genre}", de: " in {genre}" },
  "search.local": {
    en: " · from shows NotFlix already knows",
    de: " · aus Serien, die NotFlix schon kennt",
  },
  "search.nothing": { en: "Nothing found.", de: "Nichts gefunden." },
  "search.previous": { en: "‹ Previous", de: "‹ Zurück" },
  "search.next": { en: "Next ›", de: "Weiter ›" },
  "search.page": { en: "Page {page}", de: "Seite {page}" },
} satisfies Messages;
