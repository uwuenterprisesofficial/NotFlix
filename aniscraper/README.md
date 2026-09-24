# AniScraper

Small FastAPI service that searches aniworld.to and lists seasons, episodes, languages and hoster links.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python main.py                  # or: uvicorn main:app --reload --port 9000
```

Interactive docs: http://127.0.0.1:9000/docs

## Endpoints

| Method | Path | What it returns |
|---|---|---|
| GET | `/search?q=naruto` | Best match with all seasons → episodes → streams by language, plus other matches |
| GET | `/search?q=naruto&season=1` | Same, limited to one season (`season=0` = movies) |
| GET | `/search?q=naruto&streams=false` | Episodes with languages + hoster names only (one request per season, fast) |
| GET | `/search/titles?q=naruto` | Just the matching titles/slugs |
| GET | `/anime/{slug}?season=1&streams=true` | Same as `/search`, but by exact slug |
| GET | `/anime/{slug}/season/{s}/episode/{e}` | Streams of one episode |
| GET | `/search?q=naruto&source=animetoast` | animetoast.cc: best match, one entry per language variant (Ger Dub / Ger Sub …) with episodes and hoster links |
| GET | `/search?q=naruto&source=all` | Both sites side by side (`aniworld` / `animetoast` keys) |
| GET | `/animetoast/{slug}?streams=true` | One animetoast show page by slug (e.g. `naruto-ger-dub`) |
| GET | `/animetoast/{slug}/episode/{e}` | One animetoast episode with its hoster embed URLs resolved (only that episode's links are loaded) |

`/search/titles` also takes `source=` (default `all`).

### animetoast specifics

- animetoast has one page per show *and* language, so the language comes from the title ("Ger Dub", "Ger Sub", "Eng Sub").
- Episodes are listed per hoster tab; the API merges them per episode.
- Without `streams=true` the stream `url` is the site's `?link=N` page. With `streams=true` each of those pages is loaded and `url` becomes the hoster embed URL (`page_url` keeps the original).
- Everything is returned as a single "Season 1"; animetoast puts later seasons on separate pages (they show up in `other_matches`).

## Example response (shortened)

```json
{
  "query": "naruto",
  "result": {
    "slug": "naruto",
    "title": "Naruto",
    "seasons": [
      {
        "season": 1,
        "name": "Season 1",
        "episodes": [
          {
            "episode": 1,
            "title_de": "...",
            "title_en": "...",
            "url": "https://aniworld.to/anime/stream/naruto/staffel-1/episode-1",
            "hosters": ["VOE", "Filemoon"],
            "languages": ["German Dub", "German Sub"],
            "streams": {
              "German Dub": [{"hoster": "VOE", "url": "https://aniworld.to/redirect/123", "link_id": "123"}],
              "German Sub": [{"hoster": "VOE", "url": "https://aniworld.to/redirect/456", "link_id": "456"}]
            }
          }
        ]
      }
    ]
  }
}
```

## Notes

- Stream URLs are the site's `/redirect/<id>` links, which forward to the hoster page.
- Language keys: 1 = German Dub, 2 = English Sub, 3 = German Sub.
- Full series with `streams=true` means one request per episode (throttled to 5 in parallel, cached 15 min). For long shows, pass `season=`.
- The HTML selectors match the site's current layout; if aniworld changes it, adjust `scraper.py`.
