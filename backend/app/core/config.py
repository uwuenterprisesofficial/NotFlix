from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ANIWORLD_SERIES_PATH = "anime/{slug}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://notflix:notflix@localhost:5432/notflix"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me"
    frontend_url: str = "http://localhost:3000"

    mal_client_id: str = ""
    mal_client_secret: str = ""
    # AniList API client (https://anilist.co/settings/developer); empty disables AniList.
    anilist_client_id: str = ""
    anilist_client_secret: str = ""
    anilist_redirect_uri: str = "http://localhost:3000/api/auth/anilist/callback"

    # Must match the redirect URL registered at https://myanimelist.net/apiconfig.
    # The frontend proxies /api/* to this backend, so the callback lives on the frontend origin.
    mal_redirect_uri: str = "http://localhost:3000/api/auth/callback"

    # The anime catalogue (the database) answers first; its MAL data is refreshed in the
    # background after this many days (airing shows: after a day). 0 never refreshes.
    catalog_refresh_days: float = 30
    # Synopsis languages the catalogue worker looks up for every show it adds (see synopsis.py).
    catalog_synopsis_languages: str = "de"

    # Jikan (unofficial MyAnimeList API) for the genre search, which MAL's own API lacks.
    # Empty disables it: the genre search then only finds shows already in the local catalog.
    jikan_url: str = "https://api.jikan.moe/v4"

    # Local directory the analyzer reads episode files from: <media_dir>/<anime_id>/<episode>.<ext>
    media_dir: str = "/media"
    # An intro/outro analysis running longer than this is stopped and marked failed.
    analysis_timeout_minutes: float = 10

    # Where the browser reaches this API (the frontend proxies /api/* here); used for proxy URLs.
    public_api_prefix: str = "/api"

    # Self-hosted Anivexa API (English sources). Empty disables the provider.
    anivexa_url: str = ""
    # mkissa (captcha), reanime (obfuscated playlists) and animeonsen (DASH) are left out.
    anivexa_providers: str = (
        "anizone,anikoto,aniwaves,animegg,anineko,anidbapp,anibd,kaa,animedunya"
    )

    # Self-hosted ReAnime.to API (English sources, embeds only). Empty disables the provider.
    reanime_url: str = ""

    # AniWorld source, first one set wins: the bundled AniScraper service (docker compose runs it
    # at http://aniscraper:8000), another self-hosted AniWorld API, or scraping ANIWORLD_URL.
    aniscraper_url: str = ""
    aniworld_api_url: str = ""

    # AniWorld (German dub/sub). Empty disables the provider. The series path changes with site
    # redesigns, so it is configurable.
    aniworld_url: str = "https://aniworld.to"
    aniworld_series_path: str = DEFAULT_ANIWORLD_SERIES_PATH

    @field_validator("aniworld_series_path")
    @classmethod
    def _series_path(cls, value: str) -> str:
        """Empty means the default; a bare prefix like "anime/stream" gets "/{slug}" appended."""
        value = value.strip().strip("/") or DEFAULT_ANIWORLD_SERIES_PATH
        if "{slug}" not in value:
            value = f"{value}/{{slug}}"
        rest = value.replace("{slug}", "")
        if "{" in rest or "}" in rest:
            raise ValueError(f"ANIWORLD_SERIES_PATH must look like anime/{{slug}}, got {value!r}")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
