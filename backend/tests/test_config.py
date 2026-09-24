import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", "anime/{slug}"),
        ("anime/{slug}", "anime/{slug}"),
        ("/anime/stream/{slug}/", "anime/stream/{slug}"),
        ("anime/stream", "anime/stream/{slug}"),
    ],
)
def test_aniworld_series_path_is_normalised(raw, expected):
    assert Settings(aniworld_series_path=raw).aniworld_series_path == expected


def test_aniworld_series_path_rejects_stray_braces():
    # What Compose < 2.24 produced from ${ANIWORLD_SERIES_PATH:-anime/{slug}}.
    with pytest.raises(ValidationError, match="must look like anime/"):
        Settings(aniworld_series_path="anime/{slug}}")
