"""Same-origin relay for provider streams.

Browsers can't send the Referer some hosts require, and hls.js needs CORS on every playlist and
segment. The API hands out signed /proxy URLs instead; only URLs signed here are ever fetched.
"""

import re
from urllib.parse import quote, urljoin, urlsplit

from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.core.config import get_settings

TOKEN_MAX_AGE_S = 12 * 3600
_URI_ATTR = re.compile(r'URI="([^"]+)"')


class InvalidToken(ValueError):
    pass


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="notflix-stream-proxy")


def sign(url: str, headers: dict[str, str]) -> str:
    return _serializer().dumps({"u": url, "h": headers})


def unsign(token: str) -> tuple[str, dict[str, str]]:
    try:
        data = _serializer().loads(token, max_age=TOKEN_MAX_AGE_S)
    except BadSignature as e:
        raise InvalidToken("Invalid or expired stream token") from e
    url = data["u"]
    if urlsplit(url).scheme not in ("http", "https"):
        raise InvalidToken("Unsupported URL scheme")
    return url, data["h"]


def proxy_url(url: str, headers: dict[str, str]) -> str:
    prefix = get_settings().public_api_prefix.rstrip("/")
    return f"{prefix}/proxy?t={quote(sign(url, headers))}"


def is_playlist(url: str, content_type: str) -> bool:
    return "mpegurl" in content_type.lower() or urlsplit(url).path.lower().endswith(".m3u8")


def rewrite_playlist(text: str, base_url: str, headers: dict[str, str]) -> str:
    """Point every URI in an HLS playlist (variants, segments, keys, maps) back at the proxy."""

    def wrap(uri: str) -> str:
        return proxy_url(urljoin(base_url, uri), headers)

    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
        elif stripped.startswith("#"):
            lines.append(_URI_ATTR.sub(lambda m: f'URI="{wrap(m.group(1))}"', line))
        else:
            lines.append(wrap(stripped))
    return "\n".join(lines) + "\n"
