from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://notflix:notflix@localhost:5432/notflix"
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = "change-me"
    frontend_url: str = "http://localhost:3000"

    mal_client_id: str = ""
    mal_client_secret: str = ""
    # Must match the redirect URL registered at https://myanimelist.net/apiconfig.
    # The frontend proxies /api/* to this backend, so the callback lives on the frontend origin.
    mal_redirect_uri: str = "http://localhost:3000/api/auth/callback"

    # Local directory the analyzer reads episode files from: <media_dir>/<anime_id>/<episode>.<ext>
    media_dir: str = "/media"


@lru_cache
def get_settings() -> Settings:
    return Settings()
