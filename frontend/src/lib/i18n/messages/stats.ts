import type { Messages } from "../core";

type Num = (value: number, digits?: number) => string;
const fmt =
  (lang: "en" | "de"): Num =>
  (value, digits = 2) =>
    value.toLocaleString(lang === "de" ? "de-DE" : "en-US", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });

export const stats = {
  "stats.title": { en: "Your anime statistics", de: "Deine Anime-Statistiken" },
  "stats.subtitle": {
    en: "From your MyAnimeList list, compared with MAL's community scores.",
    de: "Aus deiner MyAnimeList-Liste, verglichen mit den Wertungen der MAL-Community.",
  },
  "stats.signIn": {
    en: "Sign in with MyAnimeList to see statistics about your list.",
    de: "Melde dich mit MyAnimeList an, um Statistiken zu deiner Liste zu sehen.",
  },
  "stats.syncFirst": {
    en: "Press “Sync lists” to import your list first.",
    de: "Importiere zuerst deine Liste mit „Listen synchronisieren“.",
  },

  // Loading
  "stats.preparing": {
    en: "Preparing your statistics",
    de: "Deine Statistiken werden vorbereitet",
  },
  "stats.step.loading": { en: "Loading", de: "Lade" },
  "stats.step.offline": {
    en: "Can't reach the server, retrying",
    de: "Server nicht erreichbar, versuche es erneut",
  },
  "stats.step.starting": { en: "Starting", de: "Starte" },
  "stats.step.details": {
    en: "Loading show details from MyAnimeList",
    de: "Lade Seriendetails von MyAnimeList",
  },
  "stats.step.computing": { en: "Computing statistics", de: "Berechne Statistiken" },
  "stats.progress": { en: "{step} ({done} of {total})", de: "{step} ({done} von {total})" },
  "stats.firstTime": {
    en: "The first time, every show's genres, studios and more are loaded from MyAnimeList. You can leave this page — it keeps going.",
    de: "Beim ersten Mal werden Genres, Studios und mehr für jede Serie von MyAnimeList geladen. Du kannst die Seite verlassen – es läuft weiter.",
  },
  "stats.failed": {
    en: "The statistics couldn't be computed.",
    de: "Die Statistiken konnten nicht berechnet werden.",
  },
  "stats.updating": {
    en: "Updating in the background: {progress}",
    de: "Wird im Hintergrund aktualisiert: {progress}",
  },
  "stats.updateFailed": { en: "Updating failed", de: "Aktualisierung fehlgeschlagen" },
  "stats.computedAt": { en: "Computed {when}", de: "Berechnet am {when}" },
  "stats.recalculate": { en: "Recalculate", de: "Neu berechnen" },

  // Tiles
  "stats.shows": { en: "Shows", de: "Serien" },
  "stats.scored": { en: "{count} scored", de: "{count} bewertet" },
  "stats.timeWatched": { en: "Time watched", de: "Geschaute Zeit" },
  "stats.days": { en: "{days} days", de: "{days} Tage" },
  "stats.episodes": { en: "{count} episodes", de: "{count} Folgen" },
  "stats.meanScore": { en: "Your mean score", de: "Deine Durchschnittswertung" },
  "stats.malSame": { en: "MAL: {mal} for the same shows", de: "MAL: {mal} für dieselben Serien" },
  "stats.agreement": { en: "Agreement with MAL", de: "Übereinstimmung mit MAL" },
  "stats.offBy": {
    en: "off by {points} points on average",
    de: "im Schnitt {points} Punkte daneben",
  },
  "stats.distribution": { en: "Score distribution", de: "Verteilung der Wertungen" },
  "stats.distributionInfo": {
    en: "How you score, and how MAL scores the same shows",
    de: "Wie du wertest – und wie MAL dieselben Serien wertet",
  },
  "stats.yourScore": { en: "Your score", de: "Deine Wertung" },
  "stats.malSameShows": { en: "MAL average, same shows", de: "MAL-Schnitt, dieselben Serien" },
  "stats.you": { en: "You", de: "Du" },
  "stats.mal": { en: "MAL", de: "MAL" },
  "stats.score": { en: "Score", de: "Wertung" },
  "stats.scoreN": { en: "Score {score}", de: "Wertung {score}" },
  "stats.scoreAria": {
    en: "Score {score}: you {mine}, MAL {mal}",
    de: "Wertung {score}: du {mine}, MAL {mal}",
  },
  "stats.asTable": { en: "Show as table", de: "Als Tabelle zeigen" },
  "stats.yourList": { en: "Your list", de: "Deine Liste" },
  "stats.dropRate": {
    en: "Drop rate {rate}% of finished shows",
    de: "Abbruchquote {rate} % der beendeten Serien",
  },
  "stats.median": { en: "Median score", de: "Median-Wertung" },
  "stats.spread": { en: "Score spread (σ)", de: "Streuung (σ)" },
  "stats.vsMal": { en: "vs MAL on average", de: "Im Schnitt ggü. MAL" },
  "stats.members": { en: "Typical show's MAL members", de: "MAL-Mitglieder einer typischen Serie" },
  "stats.favourites": { en: "Favourite genres & themes", de: "Lieblingsgenres & -themen" },
  "stats.favouritesInfo": {
    en: "Points above your own average score",
    de: "Punkte über deinem eigenen Schnitt",
  },
  "stats.favouritesEmpty": {
    en: "Score a few more shows to find your favourites.",
    de: "Bewerte noch ein paar Serien, um deine Favoriten zu finden.",
  },
  "stats.hated": { en: "Genres & themes you dislike", de: "Genres & Themen, die du nicht magst" },
  "stats.hatedInfo": {
    en: "Points below your average (dropped shows count against)",
    de: "Punkte unter deinem Schnitt (abgebrochene Serien zählen dagegen)",
  },
  "stats.hatedEmpty": {
    en: "Nothing you consistently dislike — yet.",
    de: "Nichts, was du durchweg nicht magst – bisher.",
  },
  "stats.tagDetail": {
    en: "{kind} · {count} shows · you {mine} · MAL {mal}",
    de: "{kind} · {count} Serien · du {mine} · MAL {mal}",
  },
  "stats.tagDropped": { en: " · {count} dropped", de: " · {count} abgebrochen" },
  "stats.tagSummary": {
    en: "{name}: {count} shows, you {mine} vs MAL {mal}",
    de: "{name}: {count} Serien, du {mine} vs. MAL {mal}",
  },
  "stats.hotTakes": { en: "Hot takes", de: "Steile Thesen" },
  "stats.breakdown": { en: "Breakdown", de: "Aufschlüsselung" },
  "stats.breakdownInfo": {
    en: "Everything on your list, by genre, theme, studio and more",
    de: "Alles auf deiner Liste, nach Genre, Thema, Studio und mehr",
  },
  "stats.model": { en: "What predicts your score", de: "Was deine Wertung vorhersagt" },
  "stats.modelInfo": {
    en: "Learned from your {count} scored shows; used for the MUST WATCH … AVOID labels",
    de: "Gelernt aus deinen {count} bewerteten Serien; genutzt für die Labels PFLICHT … MEIDEN",
  },
  "stats.modelError": {
    en: (v: { mae: number; baseline: number | null }, lang: "en" | "de") =>
      `Predictions for shows the model hadn't seen were off by ${fmt(lang)(v.mae)} points on average${v.baseline !== null ? ` — MAL's score alone is off by ${fmt(lang)(v.baseline)}` : ""}. `,
    de: (v: { mae: number; baseline: number | null }, lang: "en" | "de") =>
      `Bei Serien, die das Modell nicht kannte, lag die Vorhersage im Schnitt ${fmt(lang)(v.mae)} Punkte daneben${v.baseline !== null ? ` – MALs Wertung allein liegt ${fmt(lang)(v.baseline)} daneben` : ""}. `,
  },
  "stats.malWeight": {
    en: "Every point of MAL score is worth {weight} of yours.",
    de: "Jeder Punkt MAL-Wertung ist {weight} Punkte deiner Wertung wert.",
  },
  "stats.raises": { en: "Raises your score", de: "Hebt deine Wertung" },
  "stats.lowers": { en: "Lowers your score", de: "Senkt deine Wertung" },
  "stats.thresholds": {
    en: "Label thresholds (predicted score): must watch ≥ {a}, recommended ≥ {b}, maybe ≥ {c}, probably skip ≥ {d}, avoid below.",
    de: "Label-Grenzen (vorhergesagte Wertung): Pflicht ≥ {a}, empfohlen ≥ {b}, vielleicht ≥ {c}, eher nicht ≥ {d}, darunter meiden.",
  },
  "stats.noModel": {
    en: "Score at least 10 shows on MyAnimeList to get predictions.",
    de: "Bewerte mindestens 10 Serien auf MyAnimeList, um Prognosen zu bekommen.",
  },
  "stats.plan": {
    en: "Your plan to watch, ranked for you",
    de: "Deine geplanten Serien, für dich sortiert",
  },
  "stats.byPrediction": { en: "By predicted score", de: "Nach vorhergesagter Wertung" },
  "stats.byMal": { en: "By MAL score", de: "Nach MAL-Wertung" },

  // Breakdown table
  "kind.genre": { en: "Genres", de: "Genres" },
  "kind.theme": { en: "Themes", de: "Themen" },
  "kind.demographic": { en: "Demographics", de: "Zielgruppen" },
  "kind.studio": { en: "Studios", de: "Studios" },
  "kind.source": { en: "Source", de: "Vorlage" },
  "kind.type": { en: "Type", de: "Typ" },
  "kind.era": { en: "Decade", de: "Jahrzehnt" },
  "kind.explicit": { en: "Explicit", de: "Explizit" },
  "kindOne.genre": { en: "Genre", de: "Genre" },
  "kindOne.theme": { en: "Theme", de: "Thema" },
  "kindOne.demographic": { en: "Demographic", de: "Zielgruppe" },
  "kindOne.explicit": { en: "Explicit", de: "Explizit" },
  "kindOne.studio": { en: "Studio", de: "Studio" },
  "kindOne.source": { en: "Source", de: "Vorlage" },
  "kindOne.type": { en: "Type", de: "Typ" },
  "kindOne.era": { en: "Decade", de: "Jahrzehnt" },
  "col.name": { en: "Name", de: "Name" },
  "col.count": { en: "Shows", de: "Serien" },
  "col.countInfo": { en: "Shows on your list", de: "Serien auf deiner Liste" },
  "col.mean": { en: "You", de: "Du" },
  "col.meanInfo": { en: "Your average score", de: "Deine Durchschnittswertung" },
  "col.mal": { en: "MAL", de: "MAL" },
  "col.malInfo": {
    en: "MAL's average for the same shows",
    de: "MALs Schnitt für dieselben Serien",
  },
  "col.delta": { en: "vs MAL", de: "ggü. MAL" },
  "col.deltaInfo": {
    en: "Your score minus MAL's, on average",
    de: "Deine Wertung minus MALs, im Schnitt",
  },
  "col.affinity": { en: "Affinity", de: "Vorliebe" },
  "col.affinityInfo": {
    en: "Points above/below your own average (few shows count less)",
    de: "Punkte über/unter deinem eigenen Schnitt (wenige Serien zählen weniger)",
  },
  "col.dropped": { en: "Dropped", de: "Abgebrochen" },
  "col.droppedInfo": { en: "Dropped shows", de: "Abgebrochene Serien" },

  // Hot takes
  "take.harsh.title": { en: "Tough critic", de: "Strenge Kritik" },
  "take.harsh.text": {
    en: (v: { difference: number; mine: number; mal: number }, lang: "en" | "de") =>
      `You score ${fmt(lang)(v.difference, 1)} points lower than MAL does on the same shows (${fmt(lang)(v.mine)} vs ${fmt(lang)(v.mal)}).`,
    de: (v: { difference: number; mine: number; mal: number }, lang: "en" | "de") =>
      `Du wertest ${fmt(lang)(v.difference, 1)} Punkte niedriger als MAL bei denselben Serien (${fmt(lang)(v.mine)} vs. ${fmt(lang)(v.mal)}).`,
  },
  "take.generous.title": { en: "Easy to please", de: "Leicht zu begeistern" },
  "take.generous.text": {
    en: (v: { difference: number; mine: number; mal: number }, lang: "en" | "de") =>
      `You score ${fmt(lang)(v.difference, 1)} points higher than MAL does on the same shows (${fmt(lang)(v.mine)} vs ${fmt(lang)(v.mal)}).`,
    de: (v: { difference: number; mine: number; mal: number }, lang: "en" | "de") =>
      `Du wertest ${fmt(lang)(v.difference, 1)} Punkte höher als MAL bei denselben Serien (${fmt(lang)(v.mine)} vs. ${fmt(lang)(v.mal)}).`,
  },
  "take.agreement.contrarian": { en: "Contrarian", de: "Querdenker" },
  "take.agreement.in_tune": { en: "In tune with MAL", de: "Ganz auf MAL-Linie" },
  "take.agreement.own": { en: "Own opinion", de: "Eigene Meinung" },
  "take.agreement.text": {
    en: (v: { level: string; correlation: number }, lang: "en" | "de") =>
      `${v.level === "contrarian" ? "Your scores barely follow MAL's" : v.level === "in_tune" ? "Your scores closely follow MAL's" : "You mostly agree with MAL, with your own twists"} (correlation ${fmt(lang)(v.correlation)}).`,
    de: (v: { level: string; correlation: number }, lang: "en" | "de") =>
      `${v.level === "contrarian" ? "Deine Wertungen folgen MAL kaum" : v.level === "in_tune" ? "Deine Wertungen folgen MAL sehr genau" : "Du stimmst MAL meist zu, mit eigenen Ausreißern"} (Korrelation ${fmt(lang)(v.correlation)}).`,
  },
  "take.underrated.title": { en: "You love it, MAL doesn't", de: "Du liebst sie, MAL nicht" },
  "take.underrated.text": {
    en: (v: { score: number; mal: number }, lang: "en" | "de") =>
      `You gave it a ${v.score} — MAL's average is ${fmt(lang)(v.mal)}.`,
    de: (v: { score: number; mal: number }, lang: "en" | "de") =>
      `Du hast eine ${v.score} gegeben – MALs Schnitt liegt bei ${fmt(lang)(v.mal)}.`,
  },
  "take.overrated.title": { en: "Overrated, says you", de: "Überbewertet, findest du" },
  "take.overrated.text": {
    en: (v: { score: number; mal: number; rank: number | null }, lang: "en" | "de") =>
      `${v.rank ? `#${v.rank} on MAL, ` : ""}${fmt(lang)(v.mal)} average — you gave it a ${v.score}.`,
    de: (v: { score: number; mal: number; rank: number | null }, lang: "en" | "de") =>
      `${v.rank ? `Platz ${v.rank} auf MAL, ` : ""}Schnitt ${fmt(lang)(v.mal)} – du hast eine ${v.score} gegeben.`,
  },
  "take.dropped_acclaimed.title": { en: "Dropped a classic", de: "Einen Klassiker abgebrochen" },
  "take.dropped_acclaimed.text": {
    en: (v: { episodes: number; mal: number }, lang: "en" | "de") =>
      `You dropped it after ${v.episodes} episode${v.episodes === 1 ? "" : "s"}, despite its ${fmt(lang)(v.mal)} on MAL.`,
    de: (v: { episodes: number; mal: number }, lang: "en" | "de") =>
      `Du hast nach ${v.episodes} ${v.episodes === 1 ? "Folge" : "Folgen"} abgebrochen – trotz ${fmt(lang)(v.mal)} auf MAL.`,
  },
  "take.hidden_gem.title": { en: "Hidden gem", de: "Geheimtipp" },
  "take.hidden_gem.text": {
    en: (v: { score: number; members: number }) =>
      `You gave it a ${v.score}; only ${v.members.toLocaleString("en-US")} MAL users have it on their list.`,
    de: (v: { score: number; members: number }) =>
      `Du hast eine ${v.score} gegeben; nur ${v.members.toLocaleString("de-DE")} MAL-Nutzer haben sie auf ihrer Liste.`,
  },
  "take.tag_contrarian.title": {
    en: (v: { name: string; difference: number }) =>
      `${v.name}: ${v.difference > 0 ? "soft spot" : "not impressed"}`,
    de: (v: { name: string; difference: number }) =>
      `${v.name}: ${v.difference > 0 ? "Schwachstelle" : "nicht überzeugt"}`,
  },
  "take.tag_contrarian.text": {
    en: (v: { name: string; difference: number; scored: number }, lang: "en" | "de") =>
      `You rate ${v.name} ${fmt(lang)(Math.abs(v.difference), 1)} points ${v.difference > 0 ? "more generously" : "more harshly"} than MAL, compared with your usual (${v.scored} scored shows).`,
    de: (v: { name: string; difference: number; scored: number }, lang: "en" | "de") =>
      `Du wertest ${v.name} ${fmt(lang)(Math.abs(v.difference), 1)} Punkte ${v.difference > 0 ? "großzügiger" : "strenger"} als MAL, verglichen mit deinem Üblichen (${v.scored} bewertete Serien).`,
  },
} satisfies Messages;
