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

Sources come from providers in `backend/app/providers/`. The only built-in provider reads the `stream_sources` table:

```sql
INSERT INTO stream_sources (anime_id, episode, provider, kind, url)
VALUES (21, 1, 'my-site', 'embed', 'https://example.com/embed/one-piece-1');
```

`anime_id` is the MyAnimeList id. `kind` is `embed` (shown in an iframe) or `direct` (an mp4/m3u8 URL played by NotFlix itself). To add a site, implement the `StreamProvider` protocol and append it to `PROVIDERS`.

Skipping only works for **direct** sources. A cross-origin iframe can't be seeked or read from the outside, so for embeds the detected timestamps are only displayed.

## Intro/outro detection

On a show's page, pick an episode range and press **Analyse**. The worker then:

1. Resolves each episode's media: `MEDIA_DIR/<anime_id>/<episode>.{mkv,mp4,…}` (`./media` in docker compose), otherwise a `direct` stream source.
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
