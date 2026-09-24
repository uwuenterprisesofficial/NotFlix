# NotFlix

A Netflix-style front end for anime, backed by your MyAnimeList account:

- **Browse**: hero banner plus rows for Continue Watching, Recommended for You, My List, Watch Again, and MAL's Top Airing / Most Popular / Coming Soon.
- **Sync with MyAnimeList**: sign in with MAL OAuth. "Sync MAL" imports your list and watch progress. Finishing an episode writes your progress back to MAL. Clicking **✓ Watched** again unwatches it: MAL only stores a count, so progress goes back to the episode before.
- **Recommendations**: a genre taste profile built from your scores relative to your own average, combined with MAL community recommendations of your best-rated shows.
- **Player**: plays a direct stream (mp4/HLS) or embeds a third-party player in an `<iframe>`. The iframe isn't sandboxed because hosters refuse to play in one, so use your browser's popup/ad blocker against their ads.
- **Intro/outro detection**: compares audio fingerprints of two or more episodes to find the shared opening and ending. Results are stored in Postgres, so each episode is only analysed once, and they drive the "Skip Intro" / auto-skip controls.

## Stack

| Layer    | Tech |
|----------|------|
| Frontend | Next.js 16 (App Router, TypeScript), Tailwind CSS 4, hls.js |
| API      | FastAPI, SQLAlchemy 2 (async, psycopg 3), Alembic |
| Jobs     | RQ worker on Redis, running the audio analysis |
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

cd ../frontend
npm install
npm run dev                                 # UI on :3000
```

## Streams

The player lists every source it finds for an episode, grouped by language: German Dub, German Sub, English Sub, English Dub. The language you pick is remembered per browser, and German Dub is the default.

It resolves all sources of the language at once and plays the first **direct** stream that works (NotFlix's own player, so Skip Intro and Next Episode work). A direct stream that errors or loads nothing within 20 s is skipped, and the next one continues from the same position. When no source has a direct stream (it waits up to 8 s for one), the embedded player is the fallback. Every source and stream, marked *Direct · MP4*, *Direct · HLS* or *Embed*, is in the dropdown on the right under the video; the language dropdown (with flags) is on the left. When you continue with **Next Episode**, the same provider and hoster are preferred.

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

**Source cache.** Opening a show's page starts a background scan, run inside the API process, of every enabled provider. It covers all episodes of a short show, or the 60 around your progress in a long one. Results are stored in the `episode_sources` and `source_scans` tables. The show page and the player read that cache first; a provider is only asked again when its data is older than 6 hours (airing shows) or 7 days (finished shows), when it doesn't cover the episodes you're near, or when you press **Refresh sources**. Anivexa and AniWorld each list many episodes in one request, so only ReAnime is asked episode by episode. The show page shows how many episodes each language has, and for each episode whether it's available in your language, only in other languages, or has no stream at all.

**Direct vs. embed.** Direct streams are played by NotFlix's own player, so Skip Intro, auto-skip, subtitles and the analyzer all work. HLS and header-protected streams are relayed through `/api/proxy` using signed URLs, so the proxy only fetches URLs the backend issued. An embedded third-party player is cross-origin and can't be controlled from outside, so for embeds the intro/outro times are only displayed. When a source reports its own intro/outro times (some Anivexa providers do), those are used for that stream instead of the analysed ones.

## Intro/outro detection

On a show's page, open **More options** and press **Analyse**. It analyses the language selected in the episode list and needs at least two episodes available in it. By default it compares two episodes: the 2nd and 3rd available ones (episode 1 often has no opening, or a different cut of it), or the 1st and 2nd when there are only two. You can widen the range. The worker then:

1. Resolves each episode's media: `MEDIA_DIR/<anime_id>/<episode>.{mkv,mp4,…}` (`./media` in docker compose), otherwise the **direct** streams the providers offer in the selected language. Embedded players are never used. If a direct link fails to decode (a dead hoster link, say), the next one is tried. An episode without any direct stream in that language fails the job with a message saying which episodes lack one.
2. Decodes the audio with ffmpeg to mono 5.5 kHz and computes a 32-bit fingerprint every 100 ms (Haitsma–Kalker: signs of band-energy differences in 300–2000 Hz).
3. For each pair of neighbouring episodes, votes on time offsets using exact hash matches. At the best offsets it looks for long runs where the bit error rate stays low. A stretch of 20–200 s shared by both episodes is an opening if it sits in the first half, otherwise an ending.
4. Saves the result to `skip_segments`. Rows with `source = 'manual'` are never overwritten. Episodes that were already analysed are skipped next time, and a single new episode is compared against one that was already analysed.

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
