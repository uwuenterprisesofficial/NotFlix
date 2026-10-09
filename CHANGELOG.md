# Changelog

What's new in each version of NotFlix. The app shows the same notes (in English and German, from
`frontend/src/lib/changelog.ts`) when a new version is opened for the first time, and at
`/changelog`. Keep both in step.

**Versioning.** One version for the whole of NotFlix (`MAJOR.MINOR.PATCH`): new features raise
MINOR, fixes PATCH. For a release, set it in `desktop/package.json`, `frontend/package.json` and
`backend/pyproject.toml`, and add an entry here and to `frontend/src/lib/changelog.ts`. Then
build the desktop app (`npm run dist` in `desktop/`) and publish the server
(`scripts/publish.sh`): its image carries the new app, which every connected app downloads.

## 0.2 — 2026-10-08

- **Seasons**: a page for every season (**Seasons** in the menu). It has recommendations for
  you, highlights and underrated shows, your season completion with genre fun facts, and the
  full list with what you've watched marked. **‹ ›** and a picker move between seasons.
- **Playlist**: line up shows to watch next. After the last episode of whatever you watch, the
  next playlist show starts. It can add airing shows with new episodes by itself.
- **Up next after the last episode**: at the end of a show's last episode (the last one aired,
  for an airing show), a card suggests what's next and starts it after a countdown. That's the
  next playlist show, else the sequel, else a recommendation.
- **Caught up**: shows where you've seen every episode that's out are greyed out with a ✓ and
  move to the back of rows like Continue Watching and New Episodes. The release calendar helps
  tell how far a show has aired.
- **Prequels and sequels**: a show's page lists its whole story in order, plus its films, side
  stories and spin-offs.
- **Search filters**: hide shows you've seen, and narrow results down by MAL score and predicted
  score. The genre search answers right away and fills in while it finds more.
- **Navigation**: a back button in the top bar.
- **Watch Together, reworked**: sessions you invite a friend to. Whatever one of you opens plays
  for both, and pausing pauses both. The players stay close without stuttering. Friends can be
  added with a friend code.
- **A logo of our own**: a screen that looks back with an anime eye's catchlights, in Catchlight Rose
  (`#E11D5C`, replacing Netflix red). It's used for the app icon, the favicon, the top bar and the splash screen. See
  [brand/](brand/README.md).
- **Automatic updates**: the desktop app updates itself from its NotFlix server in the
  background and asks to restart once an update is ready. After an update it shows what's new.

## 0.1 — 2026-09-30

The first version. Your MyAnimeList and AniList lists Netflix-style, with:

- recommendations and predicted scores
- statistics
- the release calendar
- streams with intro skipping
- Watch Together
- the desktop app with its built-in server
