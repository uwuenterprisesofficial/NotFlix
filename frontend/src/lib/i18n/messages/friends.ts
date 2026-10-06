import type { Messages } from "../core";

export const friends = {
  "friends.recommend": { en: "Recommend", de: "Empfehlen" },
  "friends.recommendTitle": {
    en: "Recommend {title} to a friend",
    de: "{title} einem Freund empfehlen",
  },
  "friends.noFriends": {
    en: "You have no friends on NotFlix yet. Invite someone under Watch Together: then you can recommend shows to each other.",
    de: "Du hast noch keine Freunde auf NotFlix. Lade jemanden unter Gemeinsam schauen ein: dann könnt ihr euch Serien empfehlen.",
  },
  "friends.inviteLink": { en: "Invite a friend", de: "Freund einladen" },
  "friends.recommendedAgo": {
    en: "recommended {when}",
    de: "empfohlen {when}",
  },
  "friends.theyHaveIt": {
    en: "{status} · {episodes} episodes",
    de: "{status} · {episodes} Folgen",
  },
  "friends.message": { en: "A note (optional)", de: "Eine Notiz (optional)" },
  "friends.messagePlaceholder": {
    en: "Why they'll like it…",
    de: "Warum es ihnen gefallen wird…",
  },
  "friends.send": { en: "Send", de: "Senden" },
  "friends.sending": { en: "Sending…", de: "Sende…" },
  "friends.sent": {
    en: (v: { count: number }) =>
      v.count === 1 ? "Recommended to 1 friend." : `Recommended to ${v.count} friends.`,
    de: (v: { count: number }) =>
      v.count === 1 ? "1 Freund empfohlen." : `${v.count} Freunden empfohlen.`,
  },
  "friends.failed": {
    en: "That didn't work. Try again.",
    de: "Das hat nicht geklappt. Versuch es nochmal.",
  },
  "friends.choose": { en: "Choose at least one friend.", de: "Wähle mindestens einen Freund." },
  "friends.cancel": { en: "Cancel", de: "Abbrechen" },
  "friends.close": { en: "Close", de: "Schließen" },
  "friends.recommendsThis": {
    en: "{name} recommends this",
    de: "{name} empfiehlt dir das",
  },
  "friends.fromFriends": { en: "From your friends", de: "Von deinen Freunden" },
  "friends.fromFriendsEmpty": {
    en: "When friends recommend you a show, it shows up here.",
    de: "Wenn dir Freunde eine Serie empfehlen, erscheint sie hier.",
  },
  "friends.youRecommended": { en: "You recommended", de: "Von dir empfohlen" },
  "friends.to": { en: "to {name}", de: "an {name}" },
  "friends.from": { en: "from {name}", de: "von {name}" },
  "friends.new": { en: "New", de: "Neu" },
  "friends.notForMe": { en: "Not for me", de: "Nichts für mich" },
  "friends.takeBack": { en: "Take back", de: "Zurücknehmen" },
  "friends.notOnTheirList": { en: "Not on their list yet", de: "Noch nicht auf der Liste" },
  "friends.putAside": { en: "Not for them", de: "Nichts für sie" },
  "friends.unseen": {
    en: (v: { count: number }) =>
      v.count === 1 ? "1 new recommendation" : `${v.count} new recommendations`,
    de: (v: { count: number }) =>
      v.count === 1 ? "1 neue Empfehlung" : `${v.count} neue Empfehlungen`,
  },
  "reason.fromFriend": { en: "{name} recommends it", de: "{name} empfiehlt es" },
  "row.from-friends": { en: "From Your Friends", de: "Von deinen Freunden" },
} satisfies Messages;
