import type { Messages } from "../core";

export const playlist = {
  "nav.playlist": { en: "Playlist", de: "Playlist" },
  "playlist.title": { en: "Playlist", de: "Playlist" },
  "playlist.subtitle": {
    en: "Plays next, in this order: after the last episode of whatever you watch, the first show here with an episode to watch starts.",
    de: "Läuft als Nächstes, in dieser Reihenfolge: nach der letzten Folge von dem, was du schaust, startet die erste Serie hier mit einer Folge zum Schauen.",
  },
  "playlist.autoAiring": {
    en: "Add airing shows with new episodes automatically",
    de: "Laufende Serien mit neuen Folgen automatisch hinzufügen",
  },
  "playlist.autoAiringInfo": {
    en: "Shows you’re watching (on your list) that are airing join the playlist when there’s an episode you haven’t seen, and leave once you’ve caught up.",
    de: "Serien, die du schaust (auf deiner Liste) und die gerade laufen, kommen in die Playlist, sobald es eine Folge gibt, die du noch nicht gesehen hast, und verschwinden, wenn du aufgeholt hast.",
  },
  "playlist.empty": {
    en: "Your playlist is empty. Add shows with “+ Playlist” on their page.",
    de: "Deine Playlist ist leer. Füge Serien mit „+ Playlist“ auf ihrer Seite hinzu.",
  },
  "playlist.play": { en: "Play", de: "Abspielen" },
  "playlist.playAll": { en: "Play playlist", de: "Playlist abspielen" },
  "playlist.episode": { en: "Episode {episode}", de: "Folge {episode}" },
  "playlist.waiting": {
    en: "Caught up: waiting for the next episode",
    de: "Aufgeholt: wartet auf die nächste Folge",
  },
  "playlist.waitingFor": {
    en: "Caught up: episode {episode} airs",
    de: "Aufgeholt: Folge {episode} erscheint",
  },
  "playlist.newEpisodes": { en: "New episodes", de: "Neue Folgen" },
  "playlist.moveUp": { en: "Move up", de: "Nach oben" },
  "playlist.moveDown": { en: "Move down", de: "Nach unten" },
  "playlist.remove": { en: "Remove", de: "Entfernen" },
  "playlist.add": { en: "Playlist", de: "Playlist" },
  "playlist.added": { en: "In playlist", de: "In der Playlist" },
  "playlist.addTitle": { en: "Add to your playlist", de: "Zu deiner Playlist hinzufügen" },
  "playlist.removeTitle": {
    en: "Remove from your playlist",
    de: "Aus deiner Playlist entfernen",
  },
  "playlist.failed": {
    en: "Couldn’t save the playlist.",
    de: "Playlist konnte nicht gespeichert werden.",
  },
  "player.nextInPlaylist": { en: "Next in your playlist", de: "Als Nächstes in deiner Playlist" },
} satisfies Messages;
