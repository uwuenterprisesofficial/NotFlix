/**
 * What's new in each version of NotFlix, newest first. The desktop app shows the entries since
 * the version opened before when a new version starts for the first time, and /changelog lists
 * them all. Keep CHANGELOG.md (in the repository's root) in step with it.
 *
 * A release: bump the version in desktop/package.json, frontend/package.json and
 * backend/pyproject.toml, and add an entry here and to CHANGELOG.md.
 */
import type { Lang } from "./i18n";

type Text = Record<Lang, string>;

export type ChangelogEntry = {
  version: string;
  date: string; // YYYY-MM-DD
  title: Text;
  items: { title: Text; text: Text }[];
};

export const CHANGELOG: ChangelogEntry[] = [
  {
    version: "0.2.0",
    date: "2026-10-08",
    title: {
      en: "Seasons, playlists and what comes next",
      de: "Seasons, Playlists und was als Nächstes kommt",
    },
    items: [
      {
        title: { en: "Seasons", de: "Seasons" },
        text: {
          en: "A page for every season (Seasons in the menu): recommendations for you, highlights and underrated shows, how much of the season you've watched with genre fun facts, and the full list with what you've seen marked.",
          de: "Eine Seite für jede Season (Seasons im Menü): Empfehlungen für dich, Highlights und unterschätzte Serien, wie viel der Season du gesehen hast mit Genre-Fakten, und die ganze Liste mit allem Gesehenen markiert.",
        },
      },
      {
        title: { en: "Playlist", de: "Playlist" },
        text: {
          en: "Line up shows to watch next. After the last episode of whatever you watch, the next playlist show starts. It can add airing shows with new episodes by itself.",
          de: "Stell Serien zum Weiterschauen zusammen. Nach der letzten Folge von dem, was du schaust, startet die nächste Serie der Playlist. Laufende Serien mit neuen Folgen kann sie selbst aufnehmen.",
        },
      },
      {
        title: { en: "Up next after the last episode", de: "Als Nächstes nach der letzten Folge" },
        text: {
          en: "At the end of a show's last episode, a card suggests what to watch next (its sequel, your playlist, or a recommendation) and starts it after a countdown.",
          de: "Am Ende der letzten Folge schlägt eine Karte vor, was du als Nächstes schauen kannst (die Fortsetzung, deine Playlist oder eine Empfehlung), und startet es nach einem Countdown.",
        },
      },
      {
        title: { en: "Caught up", de: "Aufgeholt" },
        text: {
          en: "Shows where you've seen every episode that's out are greyed out with a ✓, and move to the back of rows like Continue Watching and New Episodes.",
          de: "Serien, von denen du jede erschienene Folge gesehen hast, sind ausgegraut mit ✓ und rücken in Reihen wie Weiterschauen und Neue Folgen nach hinten.",
        },
      },
      {
        title: { en: "Prequels and sequels", de: "Vorgeschichten und Fortsetzungen" },
        text: {
          en: "A show's page lists its whole story in order, plus its films, side stories and spin-offs.",
          de: "Die Seite einer Serie zeigt die ganze Geschichte der Reihe nach, dazu Filme, Nebengeschichten und Spin-offs.",
        },
      },
      {
        title: { en: "Search filters", de: "Suchfilter" },
        text: {
          en: "Hide shows you've seen, and narrow results down by MAL score and predicted score. The genre search answers right away and fills in while it finds more.",
          de: "Blende Gesehenes aus und grenze Ergebnisse nach MAL-Wertung und Vorhersage ein. Die Genre-Suche antwortet sofort und ergänzt, während sie weitere findet.",
        },
      },
      {
        title: { en: "Navigation", de: "Navigation" },
        text: {
          en: "A back button in the top bar.",
          de: "Ein Zurück-Knopf in der oberen Leiste.",
        },
      },
      {
        title: { en: "Watch Together, reworked", de: "Zusammen schauen, überarbeitet" },
        text: {
          en: "Invite a friend to a session: whatever one of you opens plays for both, pausing pauses both, and the players stay close without stuttering. Add friends with a friend code.",
          de: "Lade einen Freund zu einer Sitzung ein: was einer öffnet, läuft bei beiden, Pause pausiert beide, und die Player bleiben ohne Ruckeln beieinander. Freunde fügst du per Freundescode hinzu.",
        },
      },
      {
        title: { en: "A logo of our own", de: "Ein eigenes Logo" },
        text: {
          en: "NotFlix has its own logo now: a screen that looks back with an anime eye's sparkle, in Catchlight Rose. It's the app icon, the browser tab and the top bar.",
          de: "NotFlix hat jetzt ein eigenes Logo: ein Bildschirm, der mit dem Glanz eines Anime-Auges zurückschaut, in Catchlight Rose. Es ist App-Icon, Browser-Tab und obere Leiste.",
        },
      },
      {
        title: { en: "Automatic updates", de: "Automatische Updates" },
        text: {
          en: "The app updates itself from your NotFlix server in the background and asks you to restart once an update is ready. This changelog shows what's new after each update.",
          de: "Die App aktualisiert sich im Hintergrund von deinem NotFlix-Server und bittet um einen Neustart, sobald ein Update bereit ist. Dieses Änderungsprotokoll zeigt nach jedem Update, was neu ist.",
        },
      },
    ],
  },
  {
    version: "0.1.0",
    date: "2026-09-30",
    title: { en: "The first version", de: "Die erste Version" },
    items: [
      {
        title: { en: "NotFlix", de: "NotFlix" },
        text: {
          en: "Your MyAnimeList and AniList lists Netflix-style: recommendations and predicted scores, statistics, the release calendar, streams with intro skipping, Watch Together, and the desktop app with its built-in server.",
          de: "Deine MyAnimeList- und AniList-Listen im Netflix-Stil: Empfehlungen und vorhergesagte Wertungen, Statistiken, der Release-Kalender, Streams mit Intro-Überspringen, Zusammen schauen und die Desktop-App mit eingebautem Server.",
        },
      },
    ],
  },
];

/** "0.2.0" → [0, 2, 0], for comparing. */
function parts(version: string): number[] {
  return version.split(".").map((p) => Number.parseInt(p, 10) || 0);
}

export function newer(a: string, b: string): boolean {
  const [x, y] = [parts(a), parts(b)];
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    if ((x[i] ?? 0) !== (y[i] ?? 0)) return (x[i] ?? 0) > (y[i] ?? 0);
  }
  return false;
}

/** The entries after `previous` up to `current` (just `current`'s on a first start). */
export function changesSince(previous: string | null, current: string): ChangelogEntry[] {
  return CHANGELOG.filter(
    (e) =>
      !newer(e.version, current) && (previous ? newer(e.version, previous) : e.version === current),
  );
}

/** "0.2.0" → "0.2" */
export function shortVersion(version: string): string {
  return version.replace(/\.0$/, "");
}
