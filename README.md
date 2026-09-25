# NotFlix

A Netflix-style front end for anime, backed by your MyAnimeList account:

- **Hover previews**: hovering a poster (with a mouse) opens a bigger card, like Netflix: a muted preview of episode 1 from its opening when that's known, Play, **+** (add to Plan to watch on your linked lists), more info, MAL score and your predicted score/label, episode count, type, year, airing state with the next episode, and genres. See **Streams** for where the preview comes from.
- **Release calendar**: a **New Episodes** row on the home page and a week calendar (**Calendar** in the top bar) of what airs when (see below).
- **Browse**: hero banner plus rows for Continue Watching, Recommended for You, My List, Watch Again, and MAL's Top Airing / Most Popular / Coming Soon.
- **Sync with MyAnimeList and/or AniList**: sign in with either or both (see **Lists** below); more can be linked in Settings. With MyAnimeList: sign in with MAL OAuth. "Sync MAL" imports your list and watch progress. Finishing an episode writes your progress back to MAL. Clicking **✓ Watched** again unwatches it: MAL only stores a count, so progress goes back to the episode before.
- **Recommendations**: MAL community recommendations of your best-rated shows, ranked by your predicted score (see below), community votes and MAL's score.
- **Statistics** (`/stats`): your list compared with MAL: score distribution next to MAL's for the same shows, favourite and disliked genres/themes, a sortable breakdown by genre, theme, demographic, studio, source, type and decade, hot takes (shows you rate far above or below MAL, acclaimed shows you dropped, hidden gems, genres you judge differently), and what drives your scores.
- **Predicted scores and labels**: every show you haven't scored gets a predicted score and a label: **MUST WATCH**, **RECOMMENDED**, **MAYBE**, **PROBABLY SKIP** or **AVOID**. Labels show on posters, the banner and the detail page (with what moved the prediction). In **Settings** (gear icon) you can turn the poster labels off or show the predicted score next to them.
- **Search** (magnifier icon): MyAnimeList title search, and a genre/theme/demographic dropdown to browse top rated, most popular, newest or "best for you".
- **Player**: plays a direct stream (mp4/HLS) or embeds a third-party player in an `<iframe>`. The iframe isn't sandboxed because hosters refuse to play in one, so use your browser's popup/ad blocker against their ads.
- **Intro/outro detection**: compares audio fingerprints of two or more episodes to find the shared opening and ending. Results are stored in Postgres, so each episode is only analysed once, and they drive the "Skip Intro" / auto-skip controls.

## Stack

| Layer    | Tech |
|----------|------|
| Frontend | Next.js 16 (App Router, TypeScript), Tailwind CSS 4, hls.js |
| API      | FastAPI, SQLAlchemy 2 (async, psycopg 3), Alembic |
| Jobs     | RQ workers on Redis: the audio analysis, and the catalogue (completing shows in the background) |
| Analysis | ffmpeg for decoding, NumPy for fingerprinting and matching |
| Data     | PostgreSQL (users, list cache, recommendations, stream sources, skip segments), Redis (queue and MAL ranking cache) |

```
browser ──► Next.js :3000 ──/api/*──► FastAPI :8000 ──► Postgres
                                         │   └──────► MyAnimeList API
                                         └─ enqueue ─► Redis ─► RQ worker (ffmpeg + fingerprinting)
```

The browser only talks to Next.js. `/api/*` is proxied to FastAPI, so the session cookie is first-party and the MAL OAuth callback is `http://localhost:3000/api/auth/callback`.

## Getting started

1. Create a MAL API client at <https://myanimelist.net/apiconfig>. Choose app type **web** and set the redirect URL to `http://localhost:3000/api/auth/callback`.
2. `cp .env.example .env`, then fill in `MAL_CLIENT_ID`, `MAL_CLIENT_SECRET` and `SECRET_KEY`.
3. `docker compose up --build`
4. Open <http://localhost:3000>, sign in, and press **Sync MAL**.

### Without Docker

Needs Postgres, Redis and ffmpeg installed locally.

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload        # API on :8000
uv run rq worker analysis                   # analysis worker
uv run rq worker catalog                    # catalogue worker

cd ../frontend
npm install
npm run dev                                 # UI on :3000
```

## Streams

The player lists every source it finds for an episode, grouped by language: German Dub, German Sub, English Dub, English Sub. The language is picked automatically from the NotFlix language (see **Languages** below): dub, then sub in that language, then dub, then sub in the other. A language you pick by hand (in the player or the episode list) is remembered for that show in this browser.

It resolves all sources of the language at once and plays the first **direct** stream that works (NotFlix's own player, so Skip Intro and Next Episode work). A direct stream that errors or loads nothing within 20 s is skipped, and the next one continues from the same position. When no source has a direct stream (it waits up to 8 s for one), the embedded player is the fallback. Every source and stream, marked *Direct · MP4*, *Direct · HLS* or *Embed*, is in the dropdown on the right under the video; the language dropdown (with flags) is on the left. When you continue with **Next Episode**, the same provider and hoster are preferred. The Next Episode card appears when the detected ending starts, or 1:30 before the end when no ending was detected. Fullscreen (the button in the corner, a double-click or `f`) enlarges the whole player, so Skip Intro and Next Episode stay visible, and it stays on when the next episode starts. On iPhones, where only the video itself can go fullscreen, the overlays aren't shown in fullscreen.

Sources come from providers in `backend/app/providers/`:

| Provider | Languages | Playback | Setting |
|----------|-----------|----------|---------|
| `aniworld` | German dub/sub, some English sub | direct when AniScraper reports a `direct_url`, else iframe embed (VOE, Doodstream, …) | via the bundled AniScraper service (`ANISCRAPER_URL`), on by default |
| `animetoast` | German dub/sub (some English) | direct when AniScraper reports a `direct_url`, else iframe embed | via AniScraper (`ANISCRAPER_URL`), on by default |
| `reanime` | English sub/dub | iframe embed (flixcloud) | `REANIME_URL`, off by default |
| `anivexa` | English sub/dub | direct HLS/MP4 through the NotFlix proxy, embed fallback | `ANIVEXA_URL`, off by default |
| `database` | any | whatever you store | always on |

> **Legal note.** AniWorld and the sites Anivexa aggregates are not licensed distributors. In the EU, watching streams you know come from an obviously illegal source is itself infringement. Enabling these providers is your decision and your responsibility.

**AniScraper (default AniWorld source).** `aniscraper/` is a small FastAPI service that scrapes aniworld.to; docker compose builds and starts it next to the backend (API docs at <http://localhost:8001/docs>), and the backend uses it through `ANISCRAPER_URL=http://aniscraper:8000`. NotFlix finds a show's series with its title search (`/search/titles`), lists a season's episodes and languages in one request (`/anime/{slug}?season=N&streams=false`), and only asks for an episode's links (`/anime/{slug}/season/{s}/episode/{e}`) when you play it; the `/redirect/…` links are followed to the hoster's embed page. A 502 from AniScraper (aniworld.to unreachable) is treated as an outage, not as "series not found". AniScraper also scrapes **animetoast.cc**, which NotFlix uses as the separate `animetoast` provider. animetoast has one page per show, season *and* language ("Naruto Ger Dub", "Naruto Ger Sub"), so a show maps to a set of page slugs: NotFlix searches (`/search/titles?source=animetoast`), groups the hits by title without the language tag, and only accepts a group whose title closely matches the show's own (season-specific) title. Scans read each language page once (`/animetoast/{slug}`); playing loads just that episode's hoster embeds (`/animetoast/{slug}/episode/{e}`). If the match is wrong or missing, set the pages under **More options → AnimeToast pages** on the show page. To use another AniWorld source and drop animetoast, set `ANISCRAPER_URL=` (empty) in `.env`.

Both episode endpoints are called with `?direct=true`. Each hoster link may carry a `direct_url` (an mp4 or m3u8 URL); when it's set, NotFlix plays that file instead of the hoster's embed, and when it's `null` the embed is used. Direct URLs are fetched fresh on every play (they expire) and always go through the NotFlix proxy, because hosters tie them to the IP that asked for them, which is the same machine as the backend.

**AniWorld through your own API.** When `ANISCRAPER_URL` is empty, set `ANIWORLD_API_URL` to a service with `GET /api/series/{title}/episodes/{season}` (episodes with `hosters` and `languages`) and `GET /api/series/{title}/episodes/{season}/{episode}` (the episode's `streams`), and NotFlix uses it instead of scraping. `{title}` is the AniWorld slug, e.g. `attack-on-titan`. Scans need one request per season; the episode endpoint is only called when you play something, and its hosters become the player's server buttons. Languages map as: German audio → German Dub, German subtitles → German Sub, English subtitles → English Sub, English audio without subtitles → English Dub. A 404 (or an empty list) means "series not found"; a 5xx is treated as an outage and retried later.

**AniWorld** is otherwise scraped directly by the backend. A MAL entry is matched to an AniWorld series by trying slugs made from its titles, and the season number is taken from AniList's prequel chain. If that match is wrong, correct the slug, season or episode offset on the show's page (signed in) under **More options → German sources (AniWorld)**. AniWorld changes domains and layouts: set `ANIWORLD_URL` to a mirror, or `ANIWORLD_SERIES_PATH=anime/stream/{slug}` if series pages 404.

**Anivexa** (<https://github.com/walterwhite-69/Anivexa-API>) is a separate Node.js service that NotFlix does not ship or start. Run it yourself and set `ANIVEXA_URL` to its address. Shows are looked up by AniList id, which NotFlix maps from the MAL id. MKissa (captcha), ReAnime (obfuscated playlists) and AnimeOnsen (DASH) are left out; change the list with `ANIVEXA_PROVIDERS`. Streaming sites block most datacenter IPs, so it works best on a home server.

**ReAnime** (<https://github.com/walterwhite-69/ReAnime.to-API>) is another separate service you run yourself; set `REANIME_URL` to its address. Its default port is 8000, which the NotFlix API also uses, so start it on another port (e.g. `uvicorn reanime:app --port 8001`). NotFlix uses only its `/search` and `/servers` endpoints, and shows the flixcloud embeds like reanime.to does. Shows are matched by AniList id. ReAnime's intro/outro times are shown with its sources.

**Running Anivexa or ReAnime next to docker compose.** Inside a container, `localhost` is the container itself, so `ANIVEXA_URL=http://localhost:4000` fails with `httpx.ConnectError: All connection attempts failed`. Use `http://host.docker.internal:4000` instead; the compose file maps that name to your machine. An unreachable provider (or AniList) is skipped for a minute after a failure, and the log says why. The player loads each provider separately, so a slow one never holds up the others.

**Your own sources** go in the `stream_sources` table:

```sql
INSERT INTO stream_sources (anime_id, episode, provider, kind, url, language)
VALUES (21, 1, 'my-site', 'embed', 'https://example.com/embed/one-piece-1', 'de-sub');
```

`anime_id` is the MyAnimeList id. `kind` is `embed` (shown in an iframe) or `direct` (an mp4/m3u8 URL played by NotFlix itself).

**Source cache.** Opening a show's page starts a background scan, run inside the API process, of every enabled provider. It covers all episodes of a short show, or the 60 around your progress in a long one. Results are stored in the `episode_sources` and `source_scans` tables. The show page and the player read that cache first; a provider is only asked again when its data is older than 6 hours (airing shows) or 7 days (finished shows), when it doesn't cover the episodes you're near, or when you press **Refresh sources**. Anivexa and AniWorld each list many episodes in one request, so only ReAnime is asked episode by episode. The show page's language dropdown shows how many episodes each language has, and for each episode whether it's available in your language, only in other languages, or has no stream at all.

**Previews.** `GET /api/anime/{id}/preview?lang=de|en` returns a direct stream of episode 1 in the UI language's order (dub, then sub, then the other language), starting at its opening when that's known (from the source or the intro/outro detection). Hovering never starts a provider scan: it only uses sources already found for episode 1 (by opening the show or playing it) and stored links; when none of those has a direct link yet, at most two are resolved, and a show without any isn't tried again for half an hour. Nothing is previewed for shows that haven't aired.

**Resolved streams and the browser copy.** What a source resolves to (its playable streams) is stored in the `resolved_sources` table, so it survives restarts: direct links for 3 hours (hosters' links expire), embeds for 7 days. `GET /api/anime/{id}/streams` returns a show's whole source list plus every stored resolution in one response, with an `expires_at` (the next rescan, at most 11 hours because of the proxy links, or 30 s while a scan is still running). The player keeps it in memory and in localStorage (the 8 most recent shows), so moving to another episode, switching language or reloading makes no requests until it expires. Only a source that was never resolved is asked for, once, and the result is added to both copies. While an episode plays, the next episode's matching source is resolved in the background, so **Next Episode** starts right away with the same stream. If a stored direct link older than 10 minutes fails to play, it's fetched fresh once (`?fresh=true`). **Refresh sources** or a corrected mapping on the show page drops the browser's copy.

**Direct vs. embed.** Direct streams are played by NotFlix's own player, so Skip Intro, auto-skip, subtitles and the analyzer all work. HLS and header-protected streams are relayed through `/api/proxy` using signed URLs, so the proxy only fetches URLs the backend issued. An embedded third-party player is cross-origin and can't be controlled from outside, so for embeds the intro/outro times are only displayed. When a source reports its own intro/outro times (some Anivexa providers do), those are used for that stream instead of the analysed ones.

## Intro/outro detection

**While watching.** When a direct stream starts playing (signed in), the player asks the API to analyse that episode and the next one. Episodes that already have intro/outro times, were analysed before, or are waiting in a job are skipped (`POST /api/anime/{id}/analyze/auto`). "Detecting intro & outro…" shows under the player until the job finishes; the current episode's new times are then used right away for Skip Intro and the Next Episode card.

**By hand.** On a show's page, open **More options** and press **Analyse**. It analyses the language selected in the episode list, by default two episodes: the 2nd and 3rd available ones (episode 1 often has no opening, or a different cut of it), or the 1st and 2nd when there are only two. You can change the range. A manual analysis always recalculates its episodes and **replaces their earlier times**, including removing a time that isn't found again; times entered by hand (`source = 'manual'`) are never touched. Once an intro/outro fingerprint is saved (or, to compare, another episode was analysed), a **single episode** is enough. **Compare episodes instead of searching for the saved fingerprints** forces a comparison, e.g. when a fingerprint is doubtful.

The widget lists every analysed episode as "Episode 2: Intro 1:25 – 2:55 · Outro 21:40 – 23:10" (`GET /api/anime/{id}/analysis`), and which episodes are still being analysed. **↻ Retry** on an episode downloads it again from fresh links (`redownload`) and recalculates it, for when its times are wrong. The saved fingerprints are listed above it; **✕** removes one (`DELETE /api/anime/{id}/analysis/references/{ref}`), after which analyses compare episodes again where no other fingerprint matches and save what they find.

What the worker does:

1. Finds the episode's media: `MEDIA_DIR/<anime_id>/<episode>.{mkv,mp4,…}` (`./media` in docker compose), otherwise the **direct** streams in the selected language. It takes the cached sources and the stored links the player already resolved, so the provider isn't asked again. Embedded players are never used. If a link fails to decode, the next one is tried, and if all stored links fail, fresh ones are fetched once. An episode without any direct stream in that language fails the job with a message saying so.
2. **Searches only where the saved opening/ending play.** ffmpeg seeks before reading (`-ss`/`-t`), so over HTTP (range requests) and HLS (segments) only that part is downloaded and decoded. The episode's length comes from its header or playlist. The opening is searched from the start in 3-minute windows (plus the fingerprint's length as overlap, so one across a window edge is still whole in the next), up to the middle. The ending is searched from the end backwards, down to the opening. **Without a saved ending, the search stops once the opening is found.** A typical 24-minute episode needs two windows of about 4 minutes, or one without ending data: in a test, 40% (22%) of the file was downloaded and it took a third (a sixth) of the time.
3. **Matching** slides the saved fingerprint over the audio and computes the bit error rate at every offset, so it doesn't depend on bit-exact frames: an opening half a frame off the grid still matches (bit errors ~0.2–0.3, against ~0.5 for unrelated audio). At the best offsets, the longest stretch whose smoothed bit error rate stays below 0.35, and covers at least half the fingerprint, is the match. Its edges are widened to the fingerprint's own start/end only within the smoothing blur, so a shortened opening keeps its length.
4. **Compares two episodes** only when there's nothing to search for (a show's first analysis), when asked to (compare mode), or when a saved opening/ending isn't found anywhere (e.g. a new opening in the second cour), so it can be learned. The whole episode is then decoded and its fingerprint saved (`episode_fingerprints`, about 60 KB per 24-minute episode), so it's never downloaded again for a comparison. The job's episodes are compared with each other, or a single one with the nearest saved episode. For each pair, every 10 s block of one episode (in 5 s steps) is slid over the other, computing its bit error rate at each position; blocks that match somewhere vote for that time offset. Like the fingerprint search, this doesn't need bit-exact frames, so shared audio that sits between the two episodes' frame grids is found too (exact hash lookups found nothing there). Mostly silent blocks don't count, since silence hashes alike everywhere. Comparing two 24-minute episodes takes about half a second. At the best offsets it looks for long runs where the bit error rate stays low. A stretch of 20–200 s shared by both is an opening if it sits in the first half, otherwise an ending. **A newly found opening/ending is saved as a reference** (the most confident one per kind), unless it matches one already saved; a show can have several per kind.
5. **Saves the times** to `skip_segments`, and records which episodes each one was compared with. Rows with `source = 'manual'` are never overwritten, and an episode that was only used for comparison keeps the times it already had.

The widget on the show page lists the saved fingerprints ("Intro from episode 1 (1:30)") above the per-episode results.

**Stopping an analysis.** Every waiting or running job is listed in the widget ("Analysing episodes 2, 3… (1:05)") with a **✕**; the player's "Detecting intro & outro…" has a **Stop** link. A waiting job is taken out of the queue, a running one has its worker process killed (RQ's stop command, which also ends the ffmpeg it started); either way the job is marked failed ("Stopped"). This also clears a job that only looks like it's running because its worker died. A job running longer than `ANALYSIS_TIMEOUT_MINUTES` (default 10, in `.env`) is stopped by RQ and marked failed ("Stopped after 10 minutes"); one whose worker died without reporting is marked the same way a minute after that limit.

**When no intro is known yet.** Detection needs a direct stream and a finished analysis, so a few fallbacks keep Skip Intro working meanwhile:

- **AniSkip.** An episode without an opening of its own gets AniSkip's crowd-sourced opening/ending times (`api.aniskip.com`, by MAL id; `ANISKIP_URL`, empty to turn it off). They're stored with `source = 'aniskip'` (marked "AniSkip" under the player and in the widget) and are only a stand-in: they may be from another release of the episode, so the episode is still analysed, and the detected times replace them. An episode AniSkip doesn't have isn't asked for again for a day.
- **Retries.** An episode that was analysed without finding its opening is analysed again (at most once a day) once the show has a saved opening fingerprint, e.g. one learned from later episodes.
- **» 1:25.** While no opening is known for the playing episode, the player shows a button that jumps 85 seconds ahead (a typical opening), during the first 8 minutes and outside the credits.

## Resume watching

While a direct stream plays, the player remembers where you are in the show's current episode (`playback_positions`, one per show and signed-in user, so it follows your MAL/AniList account rather than the browser): every 15 seconds, when pausing, and when the tab is hidden or closed (`navigator.sendBeacon`, so it arrives even as the page goes away). Only the episode you're watching is kept; starting another episode of the show replaces it.

- **Resuming.** Opening that episode again starts where you stopped, with "Resumed at 2:13 · Start over" over the player for a few seconds. The show page's Play button ("Resume episode 3 at 12:40"), the banner and the cards (with a progress bar) open that episode there.
- **Finished.** A position in the last 2 minutes (the credits), or an episode marked watched, clears it. Under 15 seconds nothing is saved.
- Embedded third-party players can't report their position, so only direct streams are resumed.

API: `GET`/`PUT`/`DELETE /api/anime/{id}/position` (`POST` too, for the beacon).

## Catalogue

Every show NotFlix sees is kept in the database (the `anime` table, plus `anime_synopses` for translated synopses and the stream tables): shows you open, search results, genre results, rankings, your lists and recommendations. The catalogue always answers first:

- **Opening a show** reads it from the catalogue. Only a show that isn't in it yet is fetched from MAL right away (once). A catalogue entry is never re-fetched while you wait: when its MAL data is older than `CATALOG_REFRESH_DAYS` (default 30; airing shows after a day; `0` never), the catalogue worker refreshes it in the background.
- **Search** looks in the catalogue (titles, English titles and alternative titles, e.g. Japanese or synonyms) and in MAL. MAL's results are cached per query for a week, so the same search doesn't ask MAL again. A show already in the catalogue is shown with the catalogue's data; catalogue matches MAL doesn't rank (e.g. found by another title) are added after MAL's first page. Without MAL, or for a query under 3 characters, the catalogue alone answers. The genre search works the same way with Jikan's results.
- **New shows are added in the background.** Search results, genre results and anything else not yet complete are handed to the **catalogue worker** (`rq worker catalog`; the `catalog-worker` service in docker compose), 25 shows per job. It stores the data it was given, fetches MAL's details where they're missing or due, looks up the synopsis in every `CATALOG_SYNOPSIS_LANGUAGES` language (default `de`: AniWorld, then AnimeToast), and marks the show complete. A show is handed over at most once an hour. A source that's down isn't remembered as "no synopsis", so it's tried again.

## Release calendar

The schedule comes from AniList's public airing schedule (`airingSchedules`: every episode's Japanese air time, with the show's MAL id), stored in the `airing_schedule` table. A week is fetched from AniList when it's first shown and then at most once an hour (past weeks once a day), in the background; shows that aren't in the catalogue yet are added from AniList's data and completed by the catalogue worker. Adult shows are left out.

- **New Episodes** (home page, after Continue Watching): each show's latest episode aired in the last 3 days, newest first, shows on your list first. A card opens that episode.
- **Calendar** (`/calendar`): Monday to Sunday in your time zone, with air times, what has aired and what's coming ("in 20 h"), and a filter for your list. Streams usually follow the Japanese broadcast within hours; German releases often later.

**Episodes that haven't aired aren't looked for.** A show's next episode comes from the schedule, or from AniList for that show (checked every 3 hours, and again once the next episode's time has passed). Episodes after the last aired one aren't scanned, asked for or resolved on the streaming sites; a show that hasn't started isn't scanned at all. The show page has no Play button before episode 1 airs and says when it does, the episode grid shows upcoming episodes greyed out with their air day, and the player shows when an unaired episode airs instead of looking for sources.

## Designs

**Settings → Design** switches how NotFlix looks: **Standard** (black and red), **Communism** (red and gold, condensed capitals in Oswald, a star by the logo, a sunburst behind the page) or **Miku** (teal and pink, rounded Nunito type, a ♪ by the logo, her sleeve stripes behind the page). A design only overrides the colour and font variables in `frontend/src/app/globals.css` (`html[data-design="…"]`), so every page follows it; the choice is a cookie, so the server renders it without a flash.

## Lists: MyAnimeList and AniList

Sign in (**Sign in** in the top bar) with MyAnimeList, AniList or both; under **Settings → Your lists** you can link the other one later or remove one (not the last). Set up AniList with a client from <https://anilist.co/settings/developer> (redirect URL `http://localhost:3000/api/auth/anilist/callback`) as `ANILIST_CLIENT_ID` / `ANILIST_CLIENT_SECRET` in `.env`. An account belongs to one NotFlix user: linking one another user has moves it over.

**Sync lists** reads every linked list:

- **Show data comes from MyAnimeList**, whose ids NotFlix uses everywhere. AniList entries are matched by their MAL id (AniList's `idMal`); the few without one are skipped (the sync message says how many). A show only AniList has is shown with AniList's data at first, and its MAL details are filled in the background (the same job the statistics use; with the app's MAL client id when you have no MAL account).
- **With both lists, each is completed with what only the other has**: an entry missing on MAL is added there with the other list's status, progress and score, and the same for AniList. This runs in the background after the sync (AniList allows only a few dozen requests a minute); **Settings → Your lists** shows how far it is. Where both lists have a show, MAL's entry is what NotFlix shows; nothing already on a list is changed.
- **Progress is written to every linked list.** If one of them fails, the player says which one; it fails only when none could be saved.

## Languages

NotFlix is in **English** or **German**. Pick it under **Settings** (gear icon); until you do, your browser's language decides. The choice is a cookie, so pages rendered on the server use it too. It sets:

- **The UI**: every label, message and hot take, number and date formats, and the genre/theme names (MAL only has English ones, so the German names are NotFlix's).
- **The stream language picked first**: in German, German Dub > German Sub > English Dub > English Sub; in English, English Dub > English Sub > German Dub > German Sub. While providers are still answering, a better language the show has on other episodes is waited for instead of falling back.
- **Synopses**: MAL's are English. In German, the description from the show's AniWorld page is used (through AniScraper, or scraped from `ANIWORLD_URL`), else the one on its AnimeToast page (AniScraper's `/animetoast/{slug}` returns it as `description`; German pages are tried first), each found through the same mapping as the show's sources. It's looked up the first time the show is opened, stored in the `anime_synopses` table, and MAL's English one is shown when neither has the show (looked up again after a week).

Translations live in `frontend/src/lib/i18n/messages/`, each message with its English and German text side by side. Adding a key to only one language is a type error.

## Statistics and predictions

MAL's API returns genres, themes and demographics in one list; NotFlix splits them by MAL id as MAL's site does. Genres: Action, Adventure, Avant Garde, Award Winning, Boys Love, Comedy, Drama, Fantasy, Girls Love, Gourmet, Horror, Mystery, Romance, Sci-Fi, Slice of Life, Sports, Supernatural and Suspense. Explicit genres: Ecchi, Erotica and Hentai. Demographics: Shounen, Seinen, Shoujo, Josei and Kids. Everything else is a theme.

**The prediction** (`backend/app/services/taste.py`) is a weighted ridge regression fitted to your scored shows on every sync:

`score ≈ intercept + a·(MAL score) + b·(popularity) + Σ weight(genre, theme, demographic, studio, source, type, decade)`

Shows you dropped without a score count as low scores at half weight. Features seen on fewer than two of your shows are left out, and the ridge penalty pulls rarely seen ones towards zero, so one loved show doesn't make its genre a favourite. At least 10 scored shows are needed.

**The labels** come from where a prediction falls among the cross-validated predictions for your own list:

| Label | Predicted score among what you've watched |
|---|---|
| MUST WATCH | top 15% |
| RECOMMENDED | top 40% |
| MAYBE | middle |
| PROBABLY SKIP | bottom 30% |
| AVOID | bottom 12% |

So they adapt to how generously you score. The statistics page shows the thresholds, the model's error on shows it hadn't seen next to MAL's score alone, and the features that raise or lower your scores.

**Genre search.** MAL's API can't list shows by genre, so the genre search uses [Jikan](https://jikan.moe), an unofficial read-only MAL API (`JIKAN_URL`, cached for an hour). Without it, or when it's down, the search falls back to shows NotFlix already knows. The title search uses MAL's own search; without MAL credentials it searches the local catalog.

**Loading.** Statistics are computed in the background and cached (Redis) until your next list sync, so the page opens at once and shows progress while they're computed. The first time, listed shows that lack the details the statistics need (genre ids, studios, source, members — e.g. shows cached before those were stored) get them from MAL: from your list in a request or two, then one request per show still missing something. Shows cached before the genre ids were stored still count by their genre names in the meantime. "Sync MAL" starts the computation for the new list right away.

## Development

```bash
cd backend
uv run pytest                 # needs a notflix_test database (createdb -U notflix notflix_test);
                              # DB tests are skipped if Postgres is unreachable
uv run ruff check . && uv run ruff format .
uv run alembic revision --autogenerate -m "describe change"

cd frontend
npm run lint && npm run build
```

CI (`.github/workflows/ci.yml`) runs all of the above and checks that the migrations match the models.
