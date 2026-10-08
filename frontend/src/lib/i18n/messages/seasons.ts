import type { Messages } from "../core";

export const seasons = {
  "nav.back": { en: "Back", de: "Zurück" },
  "nav.seasons": { en: "Seasons", de: "Seasons" },

  // Caught up (every episode out watched)
  "card.caughtUp": { en: "Caught up", de: "Aufgeholt" },
  "card.watched": { en: "Watched", de: "Gesehen" },
  "card.caughtUpInfo": {
    en: "You’ve watched every episode that’s out",
    de: "Du hast jede Folge gesehen, die es gibt",
  },

  // A show's prequels and sequels
  "story.title": { en: "The story in order", de: "Die Geschichte der Reihe nach" },
  "story.related": { en: "Films, side stories & more", de: "Filme, Nebengeschichten & mehr" },
  "story.prequel": { en: "Prequel", de: "Vorgeschichte" },
  "story.sequel": { en: "Sequel", de: "Fortsetzung" },
  "story.current": { en: "This show", de: "Diese Serie" },
  "story.parent": { en: "Main story", de: "Hauptgeschichte" },
  "story.sideStory": { en: "Side story", de: "Nebengeschichte" },
  "story.spinOff": { en: "Spin-off", de: "Spin-off" },
  "story.alternative": { en: "Alternative version", de: "Alternative Fassung" },

  // The Seasons page
  "seasons.previous": { en: "Previous season", de: "Vorherige Season" },
  "seasons.next": { en: "Next season", de: "Nächste Season" },
  "seasons.now": { en: "Now", de: "Jetzt" },
  "seasons.season": { en: "Season", de: "Season" },
  "seasons.year": { en: "Year", de: "Jahr" },
  "seasons.name.winter": { en: "Winter", de: "Winter" },
  "seasons.name.spring": { en: "Spring", de: "Frühling" },
  "seasons.name.summer": { en: "Summer", de: "Sommer" },
  "seasons.name.fall": { en: "Fall", de: "Herbst" },
  "seasons.incomplete": {
    en: "MyAnimeList couldn’t be asked: these are only the shows NotFlix already knows.",
    de: "MyAnimeList war nicht erreichbar: das sind nur die Serien, die NotFlix schon kennt.",
  },
  "seasons.nothing": {
    en: "Nothing known for this season.",
    de: "Für diese Season ist nichts bekannt.",
  },
  "seasons.recommended": { en: "Recommended for you", de: "Empfohlen für dich" },
  "seasons.highlights": { en: "Highlights", de: "Highlights" },
  "seasons.underrated": { en: "Underrated", de: "Unterschätzt" },
  "seasons.underratedInfo": {
    en: "Less popular than most of the season, but predicted to suit you well.",
    de: "Weniger beliebt als der Großteil der Season, passt aber laut Vorhersage gut zu dir.",
  },
  "seasons.completion": { en: "Season completion", de: "Season-Fortschritt" },
  "seasons.watchedOf": { en: "{pct}% of the season watched", de: "{pct} % der Season gesehen" },
  "seasons.watchingPlanned": {
    en: "{watching} in progress · {planned} planned",
    de: "{watching} angefangen · {planned} geplant",
  },
  "seasons.fact.best": {
    en: "You watched {pct}% of all {genre} shows",
    de: "Du hast {pct} % aller {genre}-Serien gesehen",
  },
  "seasons.fact.all": {
    en: "Every single {genre} show: all {n} of them",
    de: "Jede einzelne {genre}-Serie: alle {n}",
  },
  "seasons.fact.biggest": {
    en: "{genre} is the season’s biggest genre ({n} shows)",
    de: "{genre} ist das größte Genre der Season ({n} Serien)",
  },
  "seasons.fact.untouched": {
    en: "Not one of the {n} {genre} shows yet",
    de: "Noch keine der {n} {genre}-Serien",
  },
  "seasons.genres": { en: "Genres watched", de: "Gesehene Genres" },
  "seasons.all": { en: "All {n} shows", de: "Alle {n} Serien" },
  "seasons.show.all": { en: "All", de: "Alle" },
  "seasons.show.unwatched": { en: "Not watched", de: "Nicht gesehen" },
  "seasons.show.watched": { en: "Watched", de: "Gesehen" },

  // Search filters
  "search.hideSeen": { en: "Hide shows I’ve seen", de: "Gesehene ausblenden" },
  "search.hideSeenInfo": {
    en: "Leaves out shows on your list as watching, completed, on hold or dropped",
    de: "Lässt Serien weg, die auf deiner Liste als schaue ich, abgeschlossen, pausiert oder abgebrochen stehen",
  },
  "search.malScore": { en: "MAL score", de: "MAL-Wertung" },
  "search.predictedScore": { en: "Predicted", de: "Vorhersage" },
  "search.min": { en: "any", de: "egal" },
  "search.max": { en: "any", de: "egal" },
  "search.addingMore": { en: "Finding more…", de: "Suche weitere…" },
} satisfies Messages;
