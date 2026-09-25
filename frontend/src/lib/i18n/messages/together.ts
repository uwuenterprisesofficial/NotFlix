import type { Messages } from "../core";

export const together = {
  "nav.together": { en: "Together", de: "Zusammen" },
  "together.title": { en: "Watch Together", de: "Zusammen schauen" },
  "together.subtitle": {
    en: "Connect with someone: recommendations from both of your lists, and a player that stays in sync.",
    de: "Verbinde dich mit jemandem: Empfehlungen aus euren beiden Listen und ein Player, der synchron bleibt.",
  },
  "together.signIn": {
    en: "Sign in to watch together.",
    de: "Melde dich an, um zusammen zu schauen.",
  },
  "together.invite": { en: "Invite someone", de: "Jemanden einladen" },
  "together.inviteInfo": {
    en: "Send this link to the person you want to watch with. It works once, for 7 days.",
    de: "Schick diesen Link an die Person, mit der du schauen willst. Er funktioniert einmal, 7 Tage lang.",
  },
  "together.copy": { en: "Copy", de: "Kopieren" },
  "together.copied": { en: "Copied", de: "Kopiert" },
  "together.creating": { en: "Creating link…", de: "Erstelle Link…" },
  "together.inviteFailed": {
    en: "Couldn’t create a link",
    de: "Link konnte nicht erstellt werden",
  },
  "together.noConnectionsYet": {
    en: "You’re not connected with anyone yet. Invite someone: once they open your link, you’ll find each other here.",
    de: "Du bist noch mit niemandem verbunden. Lade jemanden ein: sobald der Link geöffnet wird, findet ihr euch hier.",
  },
  "together.match": { en: "{score}% match", de: "{score} % Übereinstimmung" },
  "together.online": { en: "Online", de: "Online" },
  "together.watchingNow": {
    en: "Watching {title} · Episode {episode}",
    de: "Schaut {title} · Folge {episode}",
  },
  "together.join": { en: "Join", de: "Beitreten" },
  "together.open": { en: "Recommendations", de: "Empfehlungen" },

  // Invite link
  "together.joinTitle": {
    en: "{name} wants to watch with you",
    de: "{name} will mit dir schauen",
  },
  "together.joinInfo": {
    en: "Connect to get recommendations for both of you (from both of your lists and scores) and to watch in sync.",
    de: "Verbinde dich für Empfehlungen für euch beide (aus euren Listen und Bewertungen) und um synchron zu schauen.",
  },
  "together.connect": { en: "Connect with {name}", de: "Mit {name} verbinden" },
  "together.connecting": { en: "Connecting…", de: "Verbinde…" },
  "together.connectFailed": {
    en: "Couldn’t connect. The link may have been used already.",
    de: "Verbinden fehlgeschlagen. Der Link wurde vielleicht schon benutzt.",
  },
  "together.ownInvite": {
    en: "This is your own invite link: send it to the person you want to watch with.",
    de: "Das ist dein eigener Einladungslink: schick ihn an die Person, mit der du schauen willst.",
  },
  "together.alreadyConnected": {
    en: "You’re already connected with {name}.",
    de: "Du bist schon mit {name} verbunden.",
  },
  "together.signInToJoin": {
    en: "Sign in with your list to connect with {name}. You’ll come back here afterwards.",
    de: "Melde dich mit deiner Liste an, um dich mit {name} zu verbinden. Danach geht es hier weiter.",
  },
  "together.inviteGone": {
    en: "This invite doesn’t exist anymore or has expired. Ask for a new link.",
    de: "Diese Einladung gibt es nicht mehr oder sie ist abgelaufen. Frag nach einem neuen Link.",
  },

  // A connection's page
  "together.youAnd": { en: "You & {name}", de: "Du & {name}" },
  "together.tasteMatch": { en: "Taste match", de: "Geschmack" },
  "together.sharedShows": {
    en: (v: { n: number }) => `${v.n} ${v.n === 1 ? "show" : "shows"} you both watched`,
    de: (v: { n: number }) =>
      `${v.n} ${v.n === 1 ? "Serie" : "Serien"}, die ihr beide gesehen habt`,
  },
  "together.scoreAgreement": { en: "Scores agree", de: "Bewertungen stimmen überein" },
  "together.genreAgreement": { en: "Genres agree", de: "Genres stimmen überein" },
  "together.sharedGenres": { en: "You both like", de: "Ihr beide mögt" },
  "together.notEnough": {
    en: "Too few shows in common to compare yet.",
    de: "Noch zu wenige gemeinsame Serien für einen Vergleich.",
  },
  "together.disagree": { en: "Where you disagree", de: "Hier seid ihr euch uneinig" },
  "together.disconnect": { en: "Disconnect", de: "Verbindung trennen" },
  "together.disconnectConfirm": {
    en: "Disconnect from {name}? Your joint recommendations and the shared player go away.",
    de: "Verbindung mit {name} trennen? Eure gemeinsamen Empfehlungen und der geteilte Player verschwinden.",
  },
  "together.nothing": {
    en: "Nothing to recommend yet: sync your lists (Settings) so there’s something to compare.",
    de: "Noch nichts zu empfehlen: synchronisiere eure Listen (Einstellungen), damit es etwas zu vergleichen gibt.",
  },
  "together.row.continue": { en: "Continue together", de: "Zusammen weiterschauen" },
  "together.row.together": { en: "New for both of you", de: "Neu für euch beide" },
  "together.row.planned": { en: "On your lists", de: "Auf euren Listen" },
  "together.row.showTo": { en: "Show this to {name}", de: "Zeig das {name}" },
  "together.row.both_loved": { en: "You both loved", de: "Euch beiden gefallen" },
  "together.you": { en: "You", de: "Du" },
  "together.predicted": {
    en: "{name}: predicted {score}",
    de: "{name}: vorhergesagt {score}",
  },
  "together.scored": { en: "{name}: scored {score}", de: "{name}: bewertet mit {score}" },

  // Under the player
  "together.watchTogether": { en: "Watch together", de: "Zusammen schauen" },
  "together.watchingWith": { en: "Watching with {name}", de: "Du schaust mit {name}" },
  "together.here": { en: "Here", de: "Da" },
  "together.elsewhere": {
    en: "{name} is on another page",
    de: "{name} ist auf einer anderen Seite",
  },
  "together.notHere": { en: "{name} isn’t here yet", de: "{name} ist noch nicht da" },
  "together.reconnecting": { en: "Reconnecting…", de: "Verbinde neu…" },
  "together.theirStream": {
    en: "{name} watches {label} ({language}).",
    de: "{name} schaut {label} ({language}).",
  },
  "together.useTheirs": { en: "Use the same", de: "Dasselbe nehmen" },
  "together.embedNoSync": {
    en: "Embedded players can’t be synced: pick a direct stream.",
    de: "Eingebettete Player lassen sich nicht synchronisieren: wähl einen direkten Stream.",
  },
  "together.leave": { en: "Leave", de: "Verlassen" },
  "together.loading": { en: "Loading…", de: "Lade…" },
  "together.noConnections": { en: "No one to watch with yet.", de: "Noch niemand zum Schauen." },
  "together.inviteSomeone": { en: "Invite someone", de: "Jemanden einladen" },
  "together.withName": { en: "With {name}", de: "Mit {name}" },
  "together.joinPlayback": { en: "Join playback", de: "Wiedergabe beitreten" },

  // Anywhere: the partner is watching
  "together.toast": {
    en: "{name} is watching {title} · Episode {episode}",
    de: "{name} schaut {title} · Folge {episode}",
  },
  "together.dismiss": { en: "Dismiss", de: "Ausblenden" },
} satisfies Messages;
