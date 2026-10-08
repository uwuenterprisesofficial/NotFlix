"""The desktop app's updates: its latest release, served for electron-updater (the "generic"
provider asks for latest.yml, latest-linux.yml or latest-mac.yml, then the file named in it).

The release is part of the backend's image (scripts/publish.sh copies desktop/dist into
backend/releases), so updating the server updates the app too. Like every request, these need
the API key: the app sends it."""

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.core.config import get_settings

router = APIRouter(prefix="/updates", tags=["updates"])

# Plain file names only (no folders): installers, blockmaps and the latest*.yml files.
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*$")
VERSION_LINE = re.compile(r"^version:\s*(\S+)", re.MULTILINE)
CHANNELS = ("latest.yml", "latest-linux.yml", "latest-mac.yml")


class ReleaseOut(BaseModel):
    version: str | None  # None: no release on this server
    platforms: list[str]  # "windows", "linux", "mac"


def _dir() -> Path:
    return Path(get_settings().releases_dir)


@router.get("", response_model=ReleaseOut)
async def latest_release():
    """Which version of the desktop app this server hands out."""
    version, platforms = None, []
    for name, platform in zip(CHANNELS, ("windows", "linux", "mac"), strict=True):
        path = _dir() / name
        if not path.is_file():
            continue
        found = VERSION_LINE.search(path.read_text(errors="replace"))
        version = version or (found.group(1).strip("'\"") if found else None)
        platforms.append(platform)
    return ReleaseOut(version=version, platforms=platforms)


@router.get("/{name}")
async def release_file(name: str):
    if not SAFE_NAME.match(name) or name.lower() == "readme.md":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such file")
    path = _dir() / name
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such file")
    media = "text/yaml" if name.endswith(".yml") else "application/octet-stream"
    # The update files must never be cached stale; installers are versioned by name.
    headers = {"Cache-Control": "no-cache"} if name.endswith(".yml") else {}
    return FileResponse(path, media_type=media, headers=headers, filename=name)
