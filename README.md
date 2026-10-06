# NotFlix

A Netflix-style front end for anime, backed by your MyAnimeList account:

- **Hover previews**: hovering a poster (with a mouse) opens a bigger card, like Netflix: a muted preview of episode 1 from its opening when that's known, Play, **+** (add to Plan to watch on your linked lists), more info, MAL score and your predicted score/label, episode count, type, year, airing state with the next episode, and genres. See **Streams** for where the preview comes from.
- **Release calendar**: a **New Episodes** row on the home page and a week calendar (**Calendar** in the top bar) of what airs when (see below).
- **Browse**: hero banner plus rows for Continue Watching, Recommended for You, My List, Watch Again, and MAL's Top Airing / Most Popular / Coming Soon. The banner's show plays a muted preview once its episode has loaded, from the episode's beginning or from its opening when that's known (**Settings**; it can be turned off).
- **My List** (`/my-list`): what you're watching, what of your list airs this season, and what you plan to watch. Then the prequels, sequels, films and side stories of what you watched that aren't on your list yet, in two lists: those already out, and those still to come. Each list is sorted by how much you should like a show: your own score, else the predicted one, else MAL's. Each shows one row (as many as fit the width) until you click **Show all**. The relations come from AniList (50 shows per request), cached for a week.
- **Your scores**: set or change your score (1–10) on a show's page; it's saved to every linked list (a show not on your list yet goes there as completed).
- **Sync with MyAnimeList and/or AniList**: sign in with either or both (see **Lists** below); more can be linked in Settings. With MyAnimeList: sign in with MAL OAuth. "Sync MAL" imports your list and watch progress. Finishing an episode writes your progress back to MAL. Clicking **✓ Watched** again unwatches it: MAL only stores a count, so progress goes back to the episode before.
- **Recommendations**: MAL community recommendations of your best-rated shows, ranked by your predicted score (see below), community votes and MAL's score.
- **Statistics** (`/stats`): your list compared with MAL: score distribution next to MAL's for the same shows, favourite and disliked genres/themes, a sortable breakdown by genre, theme, demographic, studio, source, type and decade, hot takes (shows you rate far above or below MAL, acclaimed shows you dropped, hidden gems, genres you judge differently), and what drives your scores.
- **Predicted scores and labels**: every show you haven't scored gets a predicted score and a label: **MUST WATCH**, **RECOMMENDED**, **MAYBE**, **PROBABLY SKIP** or **AVOID**. Labels show on posters, the banner and the detail page (with what moved the prediction). In **Settings** (gear icon) you can turn the poster labels off or show the predicted score next to them.
- **Search** (magnifier icon): MyAnimeList title search, and a genre/theme/demographic dropdown to browse top rated, most popular, newest or "best for you". **With dub** keeps (or lists) shows NotFlix has found dubbed streams of in your language; cards show a DUB badge. That comes from streams NotFlix has already looked up (none of the list APIs know about dubs), so it grows as shows are opened, and every user of a server shares it.
- **Dub or sub**: **Settings** choose whether dubs or subtitles (in your language first) are picked when a show has both; a show's own choice in its episode list still wins.
- **Player**: plays a direct stream (mp4/HLS) or embeds a third-party player in an `<iframe>`. In an episode's last five minutes, the next one's stream is looked up, checked and its beginning loaded in the background, so Next Episode starts at once (with a stream known to work). The iframe isn't sandboxed because hosters refuse to play in one, so use your browser's popup/ad blocker against their ads.
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
2. `cp .env.example .env`, then fill in `MAL_CLIENT_ID`, `MAL_CLIENT_SECRET`, `SECRET_KEY` and `API_KEY` (see [API key](#api-key)); to use NotFlix in the browser, also set `WEB_API_KEY` to the same key.
3. `docker compose up --build`
4. Open <http://localhost:3000> and sign in: your list is imported by itself (the home page fills in once it's done). **Sync lists** imports it again later.

**Faster everyday use.** Plain `docker compose up` runs the development setup: the frontend is Next's dev server (every page is compiled on its first visit, and React runs its slower development build) and the backend reloads on code changes. For watching rather than developing, use the production override, which serves the optimized build:

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build
```

Code changes then need `--build` again. (Docker Compose 2.24 or newer.)

### Without Docker

Needs Postgres, Redis and ffmpeg installed locally.

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload        # API on :8000 (API_KEY in .env)
uv run rq worker analysis                   # analysis worker
uv run rq worker catalog                    # catalogue worker

cd ../frontend
npm install
API_KEY=<the API_KEY> npm run dev           # UI on :3000
```

### API key

The API answers only requests that carry its key (`API_KEY`, at least 16 characters) in the `X-API-Key` header; everything else gets `401`, including `/health` and `/docs`, and the API doesn't start without a key. Browsers never see the key: the frontend's server adds it to the requests it passes on to the API.

- **Desktop app:** you enter the key next to the server's address. It stays in the app (encrypted with the system's key store where there is one).
- **Web app:** it adds `WEB_API_KEY` (in `docker compose`; `API_KEY` in its environment otherwise). Set it to the API key to use NotFlix in a browser; anyone who can open the web app then uses the API through it, so only expose it where that's fine. Left empty, the web app adds no key and only passes on requests that bring the right one themselves: the desktop app can then connect through the web app's `/api`, and browsers get nothing.
- **Sign-in redirects** from MyAnimeList and AniList (`/auth/callback`, `/auth/anilist/callback`) are the only requests without the key: the provider sends the browser there. They only finish a sign-in that was started with the key (matched by its one-time `state`).

### Deploying on a server

The `docker-compose.yml` in the repository's root is for development: it builds from the source and mounts it into the containers. On a server, use the backend's image from the registry and [`deploy/docker-compose.yml`](deploy/docker-compose.yml) instead. That compose file runs the API, its two workers, PostgreSQL and Redis, and publishes the API on port 6500. Nothing is mounted over the image's code.

The server is for the desktop apps, and it doesn't scrape. Every stream source is switched off there (AniScraper, AniWorld, Anivexa, ReAnime), whatever the settings say. The server keeps accounts, lists, scores, friends, recommendations, Watch Together and the [shared library](#both-streams-on-this-pc-hybrid) of streams and German synopses. The desktop apps look for streams and play them on their PCs, in hybrid mode, and send what they find to the library. A show is then looked up once for everyone. There's no web app on the server, so there's nothing to open in a browser. Add the `frontend` image yourself if you want one.

**1. Build and push the image** (on your PC, from the repository):

```sh
docker login registry.uwuenterprises.de
scripts/publish.sh                     # Linux, macOS, Git Bash
.\scripts\publish.ps1                  # Windows PowerShell
```

This pushes `registry.uwuenterprises.de/notflix-backend:latest`, built for `linux/amd64`. `scripts/publish.sh backend frontend` also pushes the web app (`aniscraper` works too). To change the registry, tag or platform, use `REGISTRY=…`, `TAG=…` and `PLATFORM=…`, or `-Registry`, `-Tag` and `-Platform` in PowerShell.

**2. Set it up on the server.** Copy the two files from `deploy/` into a folder there (the rest of the repository isn't needed):

```sh
mkdir notflix && cd notflix
# copy deploy/docker-compose.yml and deploy/.env.example here, then:
cp .env.example .env
nano .env                              # fill it in, see below
docker login registry.uwuenterprises.de
docker compose pull
docker compose up -d
```

In `.env`, or as the stack's environment variables in a deploy tool (Portainer, Dokploy, Coolify, …), since the compose file reads them either way:

- `API_KEY`, `SECRET_KEY`, `POSTGRES_PASSWORD`: long random values of letters and digits, e.g. from `openssl rand -hex 32`. Avoid `$`, `@`, `%` and quotes. `POSTGRES_PASSWORD` only counts when the database is created; see below to change it later.
- `FRONTEND_URL`: the server's public address, e.g. `https://notflix.example.com`. That's your HTTPS proxy in front of port 6500, or `http://<server>:6500` without one. Sign-ins come back there and continue in the desktop app.
- The sign-in apps (`MAL_CLIENT_ID`/`_SECRET`, `ANILIST_CLIENT_ID`/`_SECRET`). Register the redirect URLs `<FRONTEND_URL>/auth/callback` (MyAnimeList) and `<FRONTEND_URL>/auth/anilist/callback` (AniList). Those are the defaults; set `MAL_REDIRECT_URI` or `ANILIST_REDIRECT_URI` only if yours differ. URLs registered for a web app, with `/api` (`<FRONTEND_URL>/api/auth/callback`), work too: the backend serves `/api/…` like `/…`. What you register at MyAnimeList must match `MAL_REDIRECT_URI` exactly.
- Any other backend setting from the repository's [`.env.example`](.env.example) can go in `.env` too. The compose file passes the whole file to the backend.

A missing `API_KEY`, `SECRET_KEY`, `FRONTEND_URL` or `POSTGRES_PASSWORD` stops `docker compose up` with a message naming it. On start, the backend migrates the database, then serves the API; the workers wait until it's healthy. `docker compose ps` should show every service up and the backend `healthy`.

**3. HTTPS in front.** Put a reverse proxy with HTTPS in front of port 6500, because the API key travels in a header and MyAnimeList wants HTTPS redirect URLs. With [Caddy](https://caddyserver.com), the whole configuration is:

```
notflix.example.com {
    reverse_proxy localhost:6500
}
```

With nginx, turn off buffering (`proxy_buffering off;`), or Watch Together's live updates (server-sent events) stall.

**4. Connect the desktop app.** Choose **Another server**, enter `https://notflix.example.com` (the backend itself, no `/api`) and the `API_KEY`. Keep **Find and play streams on this PC** ticked ([hybrid mode](#both-streams-on-this-pc-hybrid), on by default for a new server). Without it, the app has no streams, since the server doesn't look for any. This needs an app built with the built-in server (`npm run dist`, not `dist:client`).

**Updating.** Publish again from your PC, then on the server run `docker compose pull && docker compose up -d`. New migrations run by themselves when the backend starts.

**Backups.** The database is in the `pgdata` volume. To dump it, run `docker compose exec db pg_dump -U notflix notflix > notflix.sql`.

**Which build runs?** The backend's log starts with it: `docker compose logs backend | head -1` shows e.g. `NotFlix backend 8d7f82e 2026-10-06T09:30Z`, the commit and time it was published.

**`FAILED: No 'script_location' key found in configuration`** comes from an old image, or from a compose file meant for development. Check these:

- Publish again (`scripts/publish.sh`), then on the server run `docker compose pull && docker compose up -d --remove-orphans`. The first log line must show the new build.
- Use `deploy/docker-compose.yml` and nothing else. The repository's root `docker-compose.yml` (and `docker-compose.prod.yml`) build from the source and mount `./backend` over the image's code. A tool that deploys from the git repository (Portainer, Coolify, Dokploy, …) must point at `deploy/docker-compose.yml`, not the root.
- Don't override the backend's `command`. It must stay `notflix-start`, which runs the migrations and then the API.

**`API_KEY must be set to at least 16 characters`** means the setting doesn't reach the backend: the error says whether it's missing or too short. `docker compose config | grep API_KEY` shows what compose makes of it. The file must be named exactly `.env` (not `env` or `.env.txt`, as Windows may save it) and sit next to `docker-compose.yml`, or the variables must be set in your deploy tool. Don't remove the backend's `environment:` lines in the compose file: they bring the settings to it.

**`password authentication failed for user "notflix"`** means the database was created with another password. PostgreSQL only reads `POSTGRES_PASSWORD` the first time it starts with an empty volume. The development compose file uses `notflix`, and both compose files share the volume `notflix_pgdata` (same project name). The backend then prints how to fix it. Either:

- keep the data and give the database the password from `.env`: `docker compose exec db psql -U notflix -c "ALTER USER notflix PASSWORD '<POSTGRES_PASSWORD>'"`, then `docker compose restart backend`;
- or, if there's nothing to keep yet, start the database afresh, **which deletes it**: `docker compose down -v && docker compose up -d`.

Since this version, migrations no longer depend on `alembic.ini` or the working directory. An empty folder mounted over the code now stops the backend with a message that says so.

## Desktop app

`desktop/` is an Electron app for your PC. It works in one of two ways, chosen under **Settings → Server**:

- **This PC (built-in):** all of NotFlix runs on the PC, started and stopped with the app. That covers PostgreSQL, the backend and its workers, AniScraper, Anivexa, SerienStreamAPI and ffmpeg. Nothing else to install, no Docker.
- **Another server:** the app connects to a NotFlix backend running elsewhere, e.g. a home server, by its address and [API key](#api-key).

Either way the app runs the web frontend's own server on the PC (`http://127.0.0.1:47300`) and shows it in a window; that server passes `/api/*` on to the backend.

### Build it

Build on the system the app is for (Windows for Windows): the bundle holds that system's binaries. You need Node.js, [uv](https://docs.astral.sh/uv/) and git. The [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0) (for the SerienStreamAPI service) is used when installed. Without one, the build puts one into `desktop/build/work/dotnet` (Microsoft's `dotnet-install` script; no admin rights needed). Should that fail too, the app is built without the SerienStreamAPI service, with a warning (the same for Anivexa).

```sh
cd desktop
npm install
npm run dist:win        # or dist:mac, dist:linux
```

On Windows this makes two files in `desktop/dist/`, each a single executable:

- `NotFlix Setup <version>.exe`, an installer. This is the one to use: it unpacks once and starts quickly.
- `NotFlix-<version>-portable.exe`, which runs without installing. It unpacks itself (about 700 MB) on every start, so it starts slowly.

What the build does:

- `npm run server` builds the frontend into `desktop/server/`.
- `npm run stack` builds the built-in server into `desktop/build/stack/` (`scripts/prepare-stack.mjs`):
  - a portable Python 3.12 (from uv) with the backend's and AniScraper's dependencies, and the [fakeredis](https://github.com/cunla/fakeredis-py) Redis stand-in;
  - PostgreSQL 18 (from the [embedded-postgres](https://github.com/leinelissen/embedded-postgres) packages);
  - Anivexa, at a tested commit;
  - SerienStreamAPI's AniWorld service (`desktop/stack/aniworld-api/`), published as one self-contained executable;
  - ffmpeg (from imageio-ffmpeg).

  `--without=anivexa,aniworld-api` leaves those out, e.g. without the .NET SDK.
- `npm run dist:client` builds the app without the built-in server, for connecting to another server only (about 100 MB instead of 700).

For development: `npm run server`, `npm run stack`, then `npm start`.

### This PC (built-in)

On first start the app sets everything up: the database in its data folder (`%APPDATA%\notflix-desktop\server` on Windows), and its own passwords and API key. That takes about 10 seconds behind a splash screen; later starts are a bit faster. Everything listens on `127.0.0.1` only.

To sign in, create an API client at [MyAnimeList](https://myanimelist.net/apiconfig) and/or [AniList](https://anilist.co/settings/developer) and enter it under **Settings → Server**. That box shows the redirect URLs to register (`http://localhost:47300/api/auth/callback` and `…/anilist/callback`). **Save and restart** applies the settings. **Open logs** shows what each service wrote (`server/logs/`).

- **AniWorld through:** AniScraper (the default) gives direct streams where it can resolve the hoster. SerienStreamAPI gives the hosters' own players. AnimeToast always comes from AniScraper.
- **Other backend settings** (those in [`.env.example`](.env.example)): put them in `server.env` in that `server` folder, one `KEY=value` per line, and restart the app. The built-in server sets its own addresses, keys and redirect URLs; it ignores those in `server.env` (a copied Docker `.env` can't point it at `http://aniscraper:8000`).
- **Proxies:** requests between the services never go through a proxy, including one set in Windows' Internet settings.
- **Signing in:** on MyAnimeList's or AniList's pages, **← NotFlix** (top left), Alt+← or the mouse's back button returns to the app.
- **Data:** the database lives in `server/postgres`. Caches and job queues are in memory and start empty with each run.

### Another server

Choose **Another server**, enter the backend's address and its [API key](#api-key), and press **Connect**. The app checks that a NotFlix backend answers there and takes the key (`/health`), saves both, and restarts its local server. Either address works:

- the backend itself, e.g. `http://my-server:8000` (when port 8000 is reachable from the PC), or
- the web app's address with `/api`, e.g. `https://notflix.example.com/api` (this works whether or not the web app has a key of its own).

The key can be left empty later to keep the saved one. The box also shows on any page that can't reach the backend, and **File → Server settings…** opens it. Settings are kept in `config.json` in the app's data folder. Secrets there are encrypted with the system's key store where there is one, as on Windows and macOS.

**Signing in** needs nothing new at MyAnimeList or AniList: the redirect URLs stay the server's (`MAL_REDIRECT_URI`, `ANILIST_REDIRECT_URI`, `FRONTEND_URL` in the server's `.env`). The provider's page opens in the app's window and returns to the server's web app. That web app hands the sign-in back to the desktop app with a one-time token, valid for 2 minutes; only `localhost`/`127.0.0.1` addresses are accepted as targets. So `FRONTEND_URL` must be an address the PC can open.

The server must run this version too: the backend for the sign-in hand-over, and the web app if the desktop app connects through its `/api`.

### Both: streams on this PC (hybrid)

With **Another server**, tick **Find and play streams on this PC** (only in apps built with the built-in server). The server then keeps everything about you: sign-in, lists, scores, friends, Watch Together, recommendations. The built-in server starts too, without sign-in settings, and does everything about streams: it looks for an episode's sources, resolves them and relays the video, all over this PC's own connection. The server's bandwidth isn't used for video, and sites that block the server's IP still work.

Nothing is looked for twice:

- **Show data** (titles, episode counts, airing) comes from the server's catalogue (`/library/anime/{id}`, asked again after a day). So the PC needs no MyAnimeList keys.
- **The shared library:** before the PC looks for a show's sources, it takes what the server's library already knows (`/library/sources/{id}`, at most every 15 minutes per show). It only looks for episodes nobody has checked, or that went stale (6 hours for airing shows, 7 days for finished ones). What it finds goes back to the server's library (`POST /library/sources`). The server's own scans, for the web app, go there too. So the first person to open a show finds its streams, and everyone after reuses them.
- **German synopses** (from AniWorld and AnimeToast) are shared the same way. The PC asks the server first (`/library/synopses/{id}`, at most once an hour per show). When the server has none, the PC looks the synopsis up and sends it (`POST /library/synopses`). A synopsis the server has already stays.
- Sources are shared per provider *and* the way it gets them (e.g. AniWorld through AniScraper or straight from the site): option ids mean nothing to another kind of provider. Direct links aren't shared, since they expire and can be bound to the IP that fetched them; hoster embed pages are. Local files (`/media`) never are.

The library endpoints sit behind the server's API key like everything else. When the server can't be reached, streams found before still work, and the PC looks for new ones itself. If the built-in server doesn't start, the app uses the server's streams and says why under **Settings → Server**.

### Good to know

- Invite links made in the desktop app point to the web app (`FRONTEND_URL`). With the built-in server, Watch Together only works with others who can reach this PC.
- Links to other sites open in your browser; MyAnimeList's and AniList's sign-in pages stay in the window.
- Episodes start by themselves (autoplay is allowed in the app).
- Anivexa has no license of its own and SerienStreamAPI is GPL-3.0: the build fetches them, so keep the app for yourself.

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

**Source cache.** Opening a show's page starts a background scan, run inside the API process, of every enabled provider. Results are stored in the `episode_sources` and `source_scans` tables. The show page and the player read that cache first; a provider is only asked again when its data is older than 6 hours (airing shows) or 7 days (finished shows), when it doesn't cover the episodes you're near, or when you press **Refresh sources**. While the cache is fresh, a scan for episodes it doesn't cover yet only asks for those. The show page's language dropdown shows how many episodes each language has, and for each episode whether it's available in your language, only in other languages, or has no stream at all.

- **What's covered.** Providers that list a show's episodes in a request or two (AniScraper and other AniWorld APIs, AnimeToast, Anivexa, your own sources) cover every aired episode. Those asked episode by episode (ReAnime, and AniWorld when scraped directly) cover all episodes of a short show, or the 60 around your progress in a long one.
- **Stored as found.** A scan doesn't wait until it's done: every few episodes (at least once a second) what it found is stored, nearest to your progress first (the next episode, then the ones after and before it). So in a long show like One Piece your episode's sources are there in moments while the rest is still being looked for. The episode list fills in as they arrive and says how far along it is ("12 of 60 checked"); the player asks the server only for the episodes stored since its last copy (`GET /api/anime/{id}/streams?after=<cursor>`) every few seconds until the scan is done. Asking for an episode the scan hasn't reached yet waits a few seconds at most, then asks the provider for just that episode. If a scan fails midway, what it found is kept.
- **When a provider fails.** The show page says which provider failed and why (the scan's error). A failed provider isn't asked again on every page view but after 2 minutes; **Refresh sources** retries it right away, also one skipped after a connection failure. Connections to the providers are shared and reused; one dropped under a request (e.g. by AniScraper closing idle connections) is retried once on a fresh one.

**Previews.** `GET /api/anime/{id}/preview?lang=de|en` returns a direct stream of episode 1 in the UI language's order (dub, then sub, then the other language), starting at its opening when that's known (from the source or the intro/outro detection). Hovering never starts a provider scan: it only uses sources already found for episode 1 (by opening the show or playing it) and stored links; when none of those has a direct link yet, at most two are resolved, and a show without any isn't tried again for half an hour. Nothing is previewed for shows that haven't aired.

**Resolved streams and the browser copy.** What a source resolves to (its playable streams) is stored in the `resolved_sources` table, so it survives restarts: direct links for 3 hours (hosters' links expire), embeds for 7 days. `GET /api/anime/{id}/streams` returns a show's whole source list plus every stored resolution in one response, with an `expires_at` (the next rescan, at most 11 hours because of the proxy links, or 30 s while a scan is still running) and a `cursor` for fetching only what changed. The player keeps it in memory and in localStorage (the 8 most recent shows), so moving to another episode, switching language or reloading makes no requests until it expires. Only a source that was never resolved is asked for, once, and the result is added to both copies. While an episode plays, the next episode's matching source is resolved in the background, so **Next Episode** starts right away with the same stream. If a stored direct link older than 10 minutes fails to play, it's fetched fresh once (`?fresh=true`). **A stream that still won't play is remembered** (`stream_failures`: the episode, the source and its server, for 7 days; `POST/DELETE /api/anime/{id}/episodes/{n}/failures`), on the server so every device knows: next time a direct stream that worked (or wasn't tried) is picked first, the ones that failed only after those, and embedded players after that. A remembered stream that plays after all is cleared. **Refresh sources** or a corrected mapping on the show page drops the browser's copy.

**Direct vs. embed.** Direct streams are played by NotFlix's own player, so Skip Intro, auto-skip, subtitles and the analyzer all work. HLS and header-protected streams are relayed through `/api/proxy` using signed URLs, so the proxy only fetches URLs the backend issued. An embedded third-party player is cross-origin and can't be controlled from outside, so for embeds the intro/outro times are only displayed. When a source reports its own intro/outro times (some Anivexa providers do), those are used for that stream instead of the analysed ones.

### Looking ahead, by priority

Streams are looked for in three priorities. What you want now always comes first:

1. **Opening a show** (its page, the player): its scans run right away. A background scan of that show already running carries on at full speed.
2. **Lingering on a card** (0.2 s after the enlarged card opens, when nothing is known about the show yet): its episode 1 is looked for right away, and the card's preview plays as soon as a stream is found (`/preview?scan=true`).
3. **In the background:** the home page, My List, the calendar and search results hand their shows to the backend (`POST /api/prefetch`, newest page first). It looks for their streams around your next episode, but only for shows a provider has never looked at. Two shows are scanned at a time (`SCAN_WORKERS`). Whenever a worker isn't busy with a show you're waiting for, it takes the next queued show. While the shows you're waiting for need every worker, background scans hold before their next request. A show is prefetched at most once every 6 hours.

While a card's preview plays, the featured show's preview at the top of the home page pauses, and it carries on when the card closes.

In hybrid mode this all happens on your PC, and what it finds goes to the shared library. A server that doesn't scrape ignores prefetching.

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

## Admin page

**Settings → Admin** (`/admin`) shows what's going on in the background, refreshed every 5 seconds:

- **Workers and queues** (RQ): each worker, whether it's busy and with what, when it was last seen, and the `analysis` and `catalog` queues (waiting, running, failed, finished), with the latest failed jobs and their errors. Without a worker, analyses and catalogue jobs just wait.
- **In the API process:** provider scans running now (with how far they are), statistics being computed, writes to your other list, release calendar refreshes, airing checks, open Watch Together players.
- **Providers:** scans in the last 24 hours (done, failed, running), whether one is skipped after a connection failure, and its last error. **Retry now** stops skipping it and forgets its failed scans, so the next visit to a show scans it again.
- **Failed scans** and **intro/outro analyses** with their errors, and how much is stored (catalogue, sources, remembered broken streams, Redis memory).

Who may open it: the users in `ADMINS` (MAL or AniList names, or NotFlix user ids, comma-separated, in `.env`). Without `ADMINS`, everyone signed in with a list; guests never.

## Watch Together

Connect with someone, get recommendations for both of you, and watch with a synced player (**Together** in the menu).

**Connecting.** **Invite someone** creates a link (`/together/join/<code>`, valid once, for 7 days). Whoever opens it while signed in (with MyAnimeList, AniList or both) is connected with you; opened while signed out, the invite is taken up right after signing in. A connection can be removed from its page (**Disconnect**).

**Guests.** Someone without MyAnimeList or AniList can open the link and **Join as guest** with just a name. A guest is signed in on that browser like anyone else, and can watch together and invite others, but has no list: no My List, statistics, progress or resume, and the list endpoints answer 403. The recommendations then use only the inviter's list: their taste, with MAL's score and popularity standing in for the guest ("Show this to <guest>" is the inviter's favourites). If nobody in the pair has a list (two guests, or an empty list), the rows are the catalogue's **Top rated** and **Most popular** shows. A guest who signs in later keeps their connections: they become that account's user, or are merged into it if the account already has one. Removing a guest's last connection removes the guest.

**Recommendations for both** (`GET /api/together/{id}`). Each person's taste is their score predictor (see Statistics), or without one (too few scores) their genre profile plus MAL's score. How much someone would like a show is measured against their own average and spread of scores, so a generous and a strict scorer count the same. The rows:

- **Continue together**: shows you're both watching (or have on hold).
- **New for both of you**: shows neither has on their list, from the catalogue's popular shows and both of your recommendations, ranked so that both should like it (the lower of the two appeals weighs most).
- **On your lists**: planned by both, or planned by one and a good match for the other.
- **Show this to <name>** (one row for each of you): the other's favourites (a 9 or 10, or well above their average) that you haven't seen and would like.
- **You both loved** and **Where you disagree** (shows you both scored at least 3 points apart).

Each card shows both sides: a score (★9) or a predicted one (~8.4). The **taste match** combines how alike you score the shows you both watched (correlation) with how alike your genre tastes are. The result is cached until either of you syncs your list.

**Recommending a show to a friend.** On a show's page, **Recommend** lists the people you're connected with (anyone can be recommended to, guests included). Each name shows where that friend already is with the show (on their list: status, episodes, score) and whether you recommended it before. Tick one or more, add a note if you like (up to 300 characters), and **Send**. Recommending the same show to the same friend again replaces the note and counts as new for them.

- **The friend** gets a badge on **My List** in the menu (**Together** for a guest) until they open it. Their recommendations are at the top of My List under **From your friends**, with your note, and in a **From Your Friends** row on the home page. That row leaves out shows they finished or dropped. The show's page says who recommended it, with the note. **Not for me** puts one aside.
- **You** see what you recommended at the end of My List, under **You recommended**, with where each friend is with it (or that they put it aside). **Take back** removes it.
- Only recommendations between people who are still connected are shown. A guest who signs in keeps theirs.
- API: `POST /api/friends/recommendations` (`anime_id`, `connection_ids`, `message`), `GET /api/friends/recommendations` (received, sent, unseen), `POST /api/friends/recommendations/seen`, `DELETE /api/friends/recommendations/{id}`, `GET /api/friends/recommendations/anime/{id}`.

**The synced player.** **Watch together** on a show's page or under the player opens it in your room with that person (`?together=<id>` on the watch page). Each connection has one room, kept in Redis: which episode, the position at a server time, and whether it's playing. Both players follow it through server-sent events (`GET /api/together/{id}/room/events`, proxied by Next like the rest of the API) and send their own play, pause and seeks (`POST /api/together/{id}/room`), last change wins.

- Either of you can pause, play or seek; the other player does the same. A player that drifts is brought back in step by playing up to 15% faster or slower; only more than 4 s off does it jump (which means buffering). It's never corrected while it's buffering or right after a jump, so a slow stream isn't made to jump over and over. Clocks are compared with the server's.
- Alone in the room (the other person isn't on that episode), the player works exactly as without a room: it starts by itself, resumes where you stopped and is never corrected. It only keeps the room up to date with where you are, so whoever joins starts there.
- Starting another episode (Next Episode, autoplay, or picking one) takes the other person along. Opening the room on an episode starts it for both.
- Joining a room that's playing starts at its position; when the browser doesn't allow playback without a click, **Join playback** starts it.
- The bar under the player shows who you're watching with and whether they're there. When they use another stream (language or source), **Use the same** switches yours to it: different releases of an episode can be cut differently.
- While someone is watching in your room without you, a notice anywhere in NotFlix offers to **Join**.
- Only direct streams can be synced; an embedded third-party player can't be controlled.

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

The first sign-in, and linking another list, sync in the background by themselves. **Sync lists** reads every linked list:

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

**What goes into a prediction.** The regression learns your taste from your scores: genres, themes, demographics, studios, source, type and era. MyAnimeList's score is held back, so your own preferences carry more weight. Two more things are added on top:

- **The franchise:** your scores of a show's prequels, sequels, side stories and films (AniList relations), including two steps away (season 1 counts for season 3). The prediction moves 65% of the way from what the rest predicts towards your score, and the first reason on the show's page names it: "You rated Season 1 (★10)". Relations are fetched when you sync, and a show's page looks up its own when they aren't cached.
- **Fans' recommendations:** the shows you scored at least a point above your average whose MyAnimeList community recommendations include it, at 0.3 points per point. These recommendations are stored when you sync.

Fans' recommendations are capped at 2 points and show up among the reasons ("Recommended by fans of …"). Popularity can only help: a very popular show can get a boost, and a little-known one isn't marked down for it.

**Guilty Pleasure.** A show the community rates low gets this label, instead of its usual one, when it's in at least two of the six categories you watch most and your taste likes it anyway. "Low" means a MAL score under 7, and half a point under what you usually watch. The home page has a **Guilty Pleasures** row: catalogue shows like that which aren't on your list, best predicted first.

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
