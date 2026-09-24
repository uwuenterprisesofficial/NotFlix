# NotFlix

A Netflix-style front end for anime, backed by your MyAnimeList account:

- **Browse**: hero banner plus rows for Continue Watching, Recommended for You, My List, Watch Again, and MAL's Top Airing / Most Popular / Coming Soon.
- **Sync with MyAnimeList**: sign in with MAL OAuth. "Sync MAL" imports your list and watch progress. Finishing an episode writes your progress back to MAL.
- **Recommendations**: a genre taste profile built from your scores relative to your own average, combined with MAL community recommendations of your best-rated shows.
- **Player**: plays a direct stream (mp4/HLS) or embeds a third-party player in a sandboxed `<iframe>`.
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

The player lists every source it finds for an episode, grouped by language: German Dub, German Sub, English Sub, English Dub. The language you pick is remembered per browser, and German Dub is the default. If a source fails, the next one in the same language is tried automatically.

Sources come from providers in `backend/app/providers/`:

| Provider | Languages | Playback | Setting |
|----------|-----------|----------|---------|
| `aniworld` | German dub/sub, some English sub | iframe embed (VOE, Doodstream, …) | `ANIWORLD_URL`, on by default |
| `reanime` | English sub/dub | iframe embed (flixcloud) | `REANIME_URL`, off by default |
| `anivexa` | English sub/dub | direct HLS/MP4 through the NotFlix proxy, embed fallback | `ANIVEXA_URL`, off by default |
| `database` | any | whatever you store | always on |

> **Legal note.** AniWorld and the sites Anivexa aggregates are not licensed distributors. In the EU, watching streams you know come from an obviously illegal source is itself infringement. Enabling these providers is your decision and your responsibility.

**AniWorld** is scraped directly. A MAL entry is matched to an AniWorld series by trying slugs made from its titles, and the season number is taken from AniList's prequel chain. If that match is wrong, correct the slug, season or episode offset on the show's page (signed in) under **German sources (AniWorld)**. AniWorld changes domains and layouts: set `ANIWORLD_URL` to a mirror, or `ANIWORLD_SERIES_PATH=anime/stream/{slug}` if series pages 404.

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

On a show's page, pick an episode range and press **Analyse**. The worker then:

1. Resolves each episode's media: `MEDIA_DIR/<anime_id>/<episode>.{mkv,mp4,…}` (`./media` in docker compose), otherwise the first direct stream any provider offers.
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
