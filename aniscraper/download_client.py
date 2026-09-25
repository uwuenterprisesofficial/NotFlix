"""FFmpeg download client and stream-url extraction for hosters (VOE, Streamtape, Doodstream, Vidoza).

Port of the C# ``DownloadClient``: extracts the direct stream url of common host-providers
and downloads/encodes the stream via FFmpeg with progress reporting.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
import os
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from scraper import HEADERS


class UrlExtractionFailedException(Exception):
    """Raised when a stream url could not be extracted from the hoster page."""


@dataclass
class EncodingProgress:
    frames_processed: int
    fps: float
    quality: float
    output_file_size_kb: int
    time_elapsed: timedelta
    bitrate_kbps: float
    speed_multiplier: float


_RANDOM_CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

_JUNK_PARTS = ["@$", "^^", "~@", "%?", "*~", "!!", "#&"]

_ROT13_TRANSLATION = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "NOPQRSTUVWXYZABCDEFGHIJKLMnopqrstuvwxyzabcdefghijklm",
)

_VOE_VIDEO_REDIRECT_RE = re.compile(r"window\.location\.href\s*=\s*'([^']*)'")
_VOE_B64_RE = re.compile(r"var a168c='([^']+)'")
_VOE_HLS_URL_RE = re.compile(r"'hls': '(?P<hls>[^']+)'")
_STREAMTAPE_NO_ROBOT_RE = re.compile(
    r"document\.getElementById\('norobotlink'\)\.innerHTML = (.+);"
)
_STREAMTAPE_TOKEN_RE = re.compile(r"token=([^&']+)")
_DOODSTREAM_PASS_MD5_RE = re.compile(r"/pass_md5/([^/]+/[^']+)")

_MP4UPLOAD_BASE_URL = "https://www.mp4upload.com/"
_MP4UPLOAD_INPUT_REGEX = re.compile(r'<input type="hidden" name="([A-Za-z_]+)" value="(.*?)">')
_MP4UPLOAD_EMBED_SRC_RE = re.compile(
    r'player\.src\(\s*\{\s*type:\s*"[^"]*",\s*src:\s*"([^"]+)"', re.IGNORECASE
)
_MP4UPLOAD_DIRECT_FILE_RE = re.compile(
    r'https?://[^"\'\s]+\.(?:mp4|m3u8)[^"\'\s]*', re.IGNORECASE
)
_MP4UPLOAD_HEADERS = {"Referer": _MP4UPLOAD_BASE_URL, "Origin": _MP4UPLOAD_BASE_URL}
_MP4UPLOAD_PAYLOAD_D1 = {
    "op": "",
    "usr_login": "",
    "id": "",
    "fname": "",
    "referer": "",
    "method_free": "Free Download",
}
_MP4UPLOAD_PAYLOAD_D2 = {
    "op": "",
    "id": "",
    "rand": "",
    "referer": "",
    "method_free": "Free Download",
    "method_premium": "",
}

_VIDMOLY_SOURCES_RE = re.compile(
    r"sources:\s*\[\s*\{[^}]*file\s*:\s*'([^']+)'", re.IGNORECASE
)
_VIDMOLY_M3U8_RE = re.compile(
    r"https?://[^'\s\"<>]+\.m3u8[^'\s\"<>]*", re.IGNORECASE
)

_FFMPEG_ENCODING_PROGRESS_RE = re.compile(
    r"frame=\s*(\d+).*?"
    r"fps=\s*([\d.]+).*?"
    r"q=\s*(-?[\d.]+).*?"
    r"size=\s*(\d+)\s*(?:kB|KiB|MB|MiB|GB|GiB).*?"
    r"time=\s*([\d:.]+).*?"
    r"bitrate=\s*([\d.]+)\s*(?:kbits|Mbits)/s.*?"
    r"speed=\s*([\d.]+)x",
    re.DOTALL,
)


def _random_string(length: int = 10) -> str:
    return "".join(random.choice(_RANDOM_CHARACTERS) for _ in range(length))


def _shift_letters(text: str) -> str:
    return text.translate(_ROT13_TRANSLATION)


def _replace_junk(text: str) -> str:
    for junk in _JUNK_PARTS:
        text = text.replace(junk, "_")
    return text


def _shift_back(text: str, shift: int) -> str:
    return "".join(chr(ord(char) - shift) for char in text)


def _to_time_span(text: str) -> timedelta:
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S", "%M:%S"):
        try:
            dt = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError(f"Invalid time span: {text}")
    return timedelta(
        hours=dt.hour, minutes=dt.minute, seconds=dt.second, microseconds=dt.microsecond
    )


def _contains_pass_md5(text: str | None) -> bool:
    return text is not None and "/pass_md5/" in text


def _find_xpath_node(node: BeautifulSoup, xpath: str):
    if xpath == "//meta[@name='og:url']":
        return node.find("meta", attrs={"name": "og:url"})
    if xpath == "//video[@id='player']/source":
        video = node.find("video", id="player")
        return video.find("source") if video is not None else None
    if xpath == "//div[@id='ideoooolink' and @style='display:none;']":
        return node.find("div", attrs={"id": "ideoooolink", "style": "display:none;"})
    if xpath == "//script[contains(text(), '/pass_md5/')]":
        return node.find("script", string=_contains_pass_md5)
    raise ValueError(f"Unsupported XPath: {xpath}")


def _get_inner_text(node) -> str:
    if node is None:
        return ""
    return node.get_text("").strip("/").strip()


def _get_attribute_value(node, attribute_name: str) -> str:
    if node is None:
        return ""
    value = node.get(attribute_name)
    return value.strip("/") if value else ""


def _select_single_node_text(node: BeautifulSoup, xpath: str) -> str:
    return _get_inner_text(_find_xpath_node(node, xpath))


def _select_single_node_attribute(node: BeautifulSoup, xpath: str, attribute_name: str) -> str:
    return _get_attribute_value(_find_xpath_node(node, xpath), attribute_name)


def _parse_mp4upload_post_data(html: str, template: dict[str, str]) -> dict[str, str]:
    return template | dict(_MP4UPLOAD_INPUT_REGEX.findall(html))


def _extract_mp4upload_embed_src(html: str) -> str | None:
    match = _MP4UPLOAD_EMBED_SRC_RE.search(html)
    if match:
        return match.group(1)
    match = _MP4UPLOAD_DIRECT_FILE_RE.search(html)
    if match:
        return match.group(0)
    return None


def _b64url_decode(text: str) -> bytes:
    padded = text.replace("-", "+").replace("_", "/")
    padded += "=" * (-len(padded) % 4)
    return base64.b64decode(padded)


def _extract_fmoon_code(video_url: str) -> str:
    segments = [s for s in urlparse(video_url).path.split("/") if s]
    if "e" in segments:
        index = segments.index("e") + 1
        if index < len(segments):
            return segments[index]
        return ""
    return segments[-1] if segments else ""


def _select_fmoon_key_parts(key_parts: list[str], version: str) -> list[str]:
    """Select the key parts used to derive the AES key for a FMoon playback payload.

    Mirrors the selection in the site's player bundle: for ``version`` ``n`` the parts at
    one-based indices ``n`` and ``31 - n`` are used; if they are out of range, all parts
    are concatenated.
    """
    try:
        number = int(version)
    except (TypeError, ValueError):
        number = 0
    first, second = number, 31 - number
    if first < 1 or second < 1 or first > len(key_parts) or second > len(key_parts):
        return list(key_parts)
    selected: list[str] = []
    for index in (first, second):
        part = key_parts[index - 1]
        if part:
            selected.append(part)
    return selected if selected else list(key_parts)


def _fmoon_playback_key(playback: dict) -> bytes:
    return b"".join(
        _b64url_decode(part)
        for part in _select_fmoon_key_parts(
            playback.get("key_parts") or [], playback.get("version") or ""
        )
    )


class DownloadClient:
    def __init__(
        self,
        ffmpeg_location: str,
        ignore_certificate_validation: bool = False,
        logger: logging.Logger | None = None,
    ):
        self.ffmpeg_location = ffmpeg_location
        self.logger = logger
        self.client = httpx.AsyncClient(
            headers=dict(HEADERS),
            follow_redirects=True,
            verify=not ignore_certificate_validation,
            timeout=20,
        )
        self._log_info("[DownloadClient-__init__] DownloadClient has been initialized.")

    async def close(self) -> None:
        await self.client.aclose()

    @property
    def is_closed(self) -> bool:
        return self.client.is_closed

    def _log_info(self, message: str, *args) -> None:
        if self.logger is not None:
            self.logger.info(message, *args)

    def _log_error(self, message: str, *args) -> None:
        if self.logger is not None:
            self.logger.error(message, *args)

    async def _get_and_validate(self, url: str, headers: dict[str, str] | None = None) -> str:
        self._log_info("[DownloadClient-_get_and_validate] Sending HTTP request. GET: %s.", url)
        response = await self.client.get(url, headers=headers)
        response.raise_for_status()
        return response.text

    async def _get_html_root(self, url: str) -> BeautifulSoup:
        self._log_info(
            "[DownloadClient-_get_html_root] Getting HTML document: %s...", url
        )
        return BeautifulSoup(await self._get_and_validate(url), "html.parser")

    def _build_encoder_command(
        self,
        stream_url: str,
        file_path: str,
        headers: dict[str, str] | None = None,
    ) -> list[str]:
        self._log_info("[DownloadClient-_build_encoder_command] Creating FFmpeg encoder...")
        command = [self.ffmpeg_location]
        if headers:
            header_block = "\\r\\n".join(
                f"{key}: {value}" for key, value in headers.items()
            )
            command += ["-headers", header_block]
        command += ["-i", stream_url, "-v", "quiet", "-stats", "-y", "-c", "copy", file_path]
        return command

    async def get_voe_stream_url(self, video_url: str) -> str:
        web_content = await self._get_and_validate(video_url)

        redirect_match = _VOE_VIDEO_REDIRECT_RE.search(web_content)
        if redirect_match:
            video_url = redirect_match.group(1)
            root = await self._get_html_root(video_url)
        else:
            root = BeautifulSoup(web_content, "html.parser")

        self._log_info(
            "[DownloadClient-get_voe_stream_url] Extracting VOE stream url from video: %s...",
            video_url,
        )

        script_node = root.select_one("script[type='application/json']")
        if script_node is not None:
            encoded = script_node.get_text("").strip()
            if len(encoded) > 4:
                encoded = encoded[2 : len(encoded) - 4]

            decoded = _shift_letters(encoded)
            decoded = _replace_junk(decoded).replace("_", "")
            decoded = base64.b64decode(decoded).decode("utf-8")
            decoded = _shift_back(decoded, 3)
            decoded = base64.b64decode(decoded[::-1]).decode("utf-8")

            source = json.loads(decoded).get("source")
            if source is not None:
                return source

        self._log_info(
            "[DownloadClient-get_voe_stream_url] Extracting VOE stream url from video using fallback: %s...",
            video_url,
        )

        b64_match = _VOE_B64_RE.search(web_content)
        if b64_match:
            decoded = base64.b64decode(b64_match.group(1)).decode("utf-8")[::-1]
            file_url = json.loads(decoded).get("source")
            if file_url is not None:
                return file_url

        hls_match = _VOE_HLS_URL_RE.search(web_content)
        if hls_match:
            return base64.b64decode(hls_match.group("hls")).decode("utf-8")

        raise UrlExtractionFailedException(video_url)

    async def get_streamtape_stream_url(self, video_url: str) -> str:
        if "/e/" not in video_url:
            new_root = await self._get_html_root(video_url)
            video_url = _select_single_node_attribute(
                new_root, "//meta[@name='og:url']", "content"
            )

        root = await self._get_html_root(video_url.replace("/e/", "/v/"))

        self._log_info(
            "[DownloadClient-get_streamtape_stream_url] Extracting streamtape stream url from video: %s...",
            video_url,
        )

        norobot_match = _STREAMTAPE_NO_ROBOT_RE.search(str(root))
        if not norobot_match:
            raise UrlExtractionFailedException(video_url)

        token_match = _STREAMTAPE_TOKEN_RE.search(norobot_match.group(1))
        if not token_match:
            raise UrlExtractionFailedException(video_url)

        host_url = _select_single_node_text(
            root, "//div[@id='ideoooolink' and @style='display:none;']"
        )
        return f"https://{host_url}&token={token_match.group(1)}&dl=1s"

    async def get_doodstream_stream_url(self, video_url: str) -> str:
        root = await self._get_html_root(video_url)

        self._log_info(
            "[DownloadClient-get_doodstream_stream_url] Extracting doodstream stream url from video: %s...",
            video_url,
        )

        js = _select_single_node_text(root, "//script[contains(text(), '/pass_md5/')]")
        match = _DOODSTREAM_PASS_MD5_RE.search(js)
        if not match:
            raise UrlExtractionFailedException(video_url)

        pass_md5 = match.group(1)
        stream_url = await self._get_and_validate(
            f"https://dood.li/pass_md5/{pass_md5}", headers={"Referer": video_url}
        )
        expiry = int(time.time() * 1000)
        return f"{stream_url}{_random_string(10)}?token={pass_md5}&expiry={expiry}"

    async def get_vidoza_stream_url(self, video_url: str) -> str:
        root = await self._get_html_root(video_url)

        self._log_info(
            "[DownloadClient-get_vidoza_stream_url] Extracting vidoza stream url from video: %s...",
            video_url,
        )

        return _select_single_node_attribute(root, "//video[@id='player']/source", "src")

    async def get_mp4upload_stream_url(self, video_url: str) -> str:
        """Resolve the direct file url of an MP4Upload page.

        Embed pages (``/embed-<id>.html``) expose the file url in the videojs player
        config. Regular pages use the free-download method: submit the two-step form and
        read the direct file url from the ``Location`` header of the final request.
        """
        self._log_info(
            "[DownloadClient-get_mp4upload_stream_url] Extracting mp4upload stream url from video: %s...",
            video_url,
        )

        initial = await self.client.get(video_url, headers=_MP4UPLOAD_HEADERS)
        initial.raise_for_status()
        page_url = str(initial.url)

        if "/embed-" in page_url:
            direct_url = _extract_mp4upload_embed_src(initial.text)
            if direct_url:
                return direct_url
            raise UrlExtractionFailedException(video_url)

        post_data_1 = _parse_mp4upload_post_data(
            initial.text, dict(_MP4UPLOAD_PAYLOAD_D1)
        )
        first_post = await self.client.post(
            page_url, data=post_data_1, headers=_MP4UPLOAD_HEADERS
        )
        first_post.raise_for_status()

        post_data_2 = _parse_mp4upload_post_data(
            first_post.text, dict(_MP4UPLOAD_PAYLOAD_D2)
        )
        download_req = await self.client.post(
            _MP4UPLOAD_BASE_URL + "F1",
            data=post_data_2,
            headers={**_MP4UPLOAD_HEADERS, "Referer": page_url},
            follow_redirects=False,
        )

        file_url = download_req.headers.get("Location")
        if not file_url:
            raise UrlExtractionFailedException(video_url)
        return file_url

    async def get_vidmoly_stream_url(self, video_url: str) -> str:
        self._log_info(
            "[DownloadClient-get_vidmoly_stream_url] Extracting vidmoly stream url from video: %s...",
            video_url,
        )

        web_content = await self._get_and_validate(video_url)
        sources_match = _VIDMOLY_SOURCES_RE.search(web_content)
        if sources_match:
            return sources_match.group(1)
        m3u8_match = _VIDMOLY_M3U8_RE.search(web_content)
        if m3u8_match:
            return m3u8_match.group(0)
        raise UrlExtractionFailedException(video_url)

    async def get_fmoon_stream_url(self, video_url: str) -> str:
        self._log_info(
            "[DownloadClient-get_fmoon_stream_url] Extracting fmoon stream url from video: %s...",
            video_url,
        )

        response = await self.client.get(video_url, follow_redirects=True)
        response.raise_for_status()
        final_url = str(response.url)

        code = _extract_fmoon_code(final_url)
        if not code:
            raise UrlExtractionFailedException(video_url)

        parsed = urlparse(final_url)
        api_url = f"{parsed.scheme}://{parsed.netloc}/api/videos/{code}/"
        response = await self.client.get(api_url, headers={"Referer": final_url})
        response.raise_for_status()
        data = response.json()

        playback = data.get("playback")
        if not isinstance(playback, dict):
            raise UrlExtractionFailedException(video_url)

        iv = _b64url_decode(playback.get("iv") or "")
        ciphertext = _b64url_decode(playback.get("payload") or "")
        try:
            plaintext = AESGCM(_fmoon_playback_key(playback)).decrypt(iv, ciphertext, None)
        except Exception:
            raise UrlExtractionFailedException(video_url)

        config = json.loads(plaintext.decode("utf-8"))
        sources = [
            source
            for source in (config.get("sources") or [])
            if isinstance(source, dict) and source.get("url")
        ]
        if not sources:
            raise UrlExtractionFailedException(video_url)

        sources.sort(
            key=lambda s: (s.get("height") or 0, s.get("bitrate_kbps") or 0),
            reverse=True,
        )
        return sources[0]["url"]

    async def resolve_direct(
        self, hoster: str | None, url: str
    ) -> tuple[str | None, str | None]:
        """Resolve the direct stream url for a hoster embed page.

        ``url`` may be the hoster page itself or a (server-side) redirect to it. Returns
        ``(direct_url, None)`` on success or ``(None, error)`` if extraction failed. Returns
        ``(None, None)`` for unsupported hosters.
        """
        name = (hoster or "").lower()
        host = urlparse(url).hostname or ""
        try:
            if "voe" in name or "voe" in host:
                return await self.get_voe_stream_url(url), None
            if "streamtape" in name or "streamtape" in host:
                return await self.get_streamtape_stream_url(url), None
            if "dood" in name or "dood" in host:
                return await self.get_doodstream_stream_url(url), None
            if "vidoza" in name or "vidoza" in host:
                return await self.get_vidoza_stream_url(url), None
            #if "mp4upload" in name or "mp4upload" in host: Disabled since the direct link is still vorbidden
            #    return await self.get_mp4upload_stream_url(url), None
            if "vidmoly" in name or "vidmoly" in host or "vidm" in name:
                return await self.get_vidmoly_stream_url(url), None
            if "fmoon" in name or "filemoon" in name or "filemoon" in host or "byse" in host:
                return await self.get_fmoon_stream_url(url), None
            return None, None
        except Exception as ex:
            self._log_error("[DownloadClient-resolve_direct] Failed: %s", ex)
            return None, str(ex)

    def _parse_progress_line(self, line: str) -> EncodingProgress | None:
        match = _FFMPEG_ENCODING_PROGRESS_RE.search(line)
        if not match:
            return None
        return EncodingProgress(
            frames_processed=int(match.group(1)),
            fps=float(match.group(2)),
            quality=float(match.group(3)),
            output_file_size_kb=int(match.group(4)),
            time_elapsed=_to_time_span(match.group(5)),
            bitrate_kbps=float(match.group(6)),
            speed_multiplier=float(match.group(7)),
        )

    async def download(
        self,
        stream_url: str,
        file_path: str,
        headers: dict[str, str] | None = None,
        progress: Callable[[EncodingProgress], None] | None = None,
        cancellation_token: asyncio.Event | None = None,
    ) -> None:
        """Download & encode a stream to ``file_path`` via FFmpeg.

        ``progress`` is called for every stats line parsed from FFmpeg's stderr. If
        ``cancellation_token`` (an ``asyncio.Event``) is set, the encoder is killed, the
        partially written file is removed and the call raises ``asyncio.CancelledError``.
        """
        self._log_info("[DownloadClient-download] Starting to download & encode stream...")

        command = self._build_encoder_command(stream_url, file_path, headers)
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )

        async def _consume_stderr() -> None:
            if process.stderr is None:
                return
            async for raw_line in process.stderr:
                if progress is not None:
                    parsed = self._parse_progress_line(
                        raw_line.decode("utf-8", errors="replace")
                    )
                    if parsed is not None:
                        progress(parsed)

        stderr_task = asyncio.create_task(_consume_stderr())
        wait_task = asyncio.ensure_future(process.wait())

        async def _kill_and_cleanup() -> None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            try:
                await asyncio.wait_for(asyncio.shield(wait_task), timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception as ex:
                    self._log_error(
                        "[DownloadClient-download] Failed to kill encoder and delete file: %s",
                        ex,
                    )

        cancel_task: asyncio.Task | None = None
        try:
            if cancellation_token is not None:
                cancel_task = asyncio.ensure_future(cancellation_token.wait())
                done, _ = await asyncio.wait(
                    {wait_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
                )
                if wait_task not in done:
                    await _kill_and_cleanup()
                    raise asyncio.CancelledError
                wait_task.result()
            else:
                await wait_task
        except asyncio.CancelledError:
            await _kill_and_cleanup()
            raise
        finally:
            stderr_task.cancel()
            if cancel_task is not None and not cancel_task.done():
                cancel_task.cancel()
