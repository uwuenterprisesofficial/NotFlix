from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import StreamSource

MEDIA_EXTENSIONS = (".mkv", ".mp4", ".webm", ".m4a", ".mp3", ".opus", ".aac", ".wav")


class MediaNotFound(LookupError):
    pass


def resolve_media(db: Session, anime_id: int, episode: int) -> str:
    """Find something ffmpeg can decode for an episode.

    Embedded iframes can't be analysed (their audio is cross-origin), so the analyzer needs either
    a local file at <MEDIA_DIR>/<anime_id>/<episode>.<ext> or a "direct" stream source URL.
    """
    folder = Path(get_settings().media_dir) / str(anime_id)
    for ext in MEDIA_EXTENSIONS:
        candidate = folder / f"{episode}{ext}"
        if candidate.is_file():
            return str(candidate)

    direct = db.scalar(
        select(StreamSource.url).where(
            StreamSource.anime_id == anime_id,
            StreamSource.episode == episode,
            StreamSource.kind == "direct",
        )
    )
    if direct:
        return direct
    raise MediaNotFound(
        f"No media for anime {anime_id} episode {episode}: add {folder}/{episode}.mkv "
        "or a direct stream source"
    )
