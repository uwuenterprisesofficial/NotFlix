import re
import subprocess

import numpy as np

SAMPLE_RATE = 5512
PROBE_TIMEOUT_S = 60
_DURATION = re.compile(r"Duration: (\d+):(\d\d):(\d\d(?:\.\d+)?)")


class AudioDecodeError(RuntimeError):
    pass


def _header_args(headers: dict[str, str] | None) -> list[str]:
    return ["-headers", "".join(f"{k}: {v}\r\n" for k, v in headers.items())] if headers else []


def load_audio(
    source: str,
    headers: dict[str, str] | None = None,
    sample_rate: int = SAMPLE_RATE,
    start_s: float | None = None,
    duration_s: float | None = None,
) -> np.ndarray:
    """Decode any ffmpeg-readable file or URL into mono float32 PCM; with `start_s` and/or
    `duration_s` only that part. ffmpeg seeks before reading, so over HTTP (range requests)
    and HLS (segments) only that part is downloaded."""
    # -ss before -i seeks the input instead of decoding everything up to that point.
    window = ["-ss", f"{start_s:.3f}"] if start_s else []
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error",
        *_header_args(headers),
        *window,
        "-i", source,
        *(["-t", f"{duration_s:.3f}"] if duration_s else []),
        "-vn", "-ac", "1", "-ar", str(sample_rate),
        "-f", "f32le", "-",
    ]  # fmt: skip
    try:
        proc = subprocess.run(cmd, capture_output=True, check=False)
    except FileNotFoundError as e:
        raise AudioDecodeError("ffmpeg is not installed") from e
    if proc.returncode != 0:
        raise AudioDecodeError(proc.stderr.decode(errors="replace")[-500:])
    return np.frombuffer(proc.stdout, dtype=np.float32)


def probe_duration(source: str, headers: dict[str, str] | None = None) -> float | None:
    """The media's length in seconds from its header or playlist (nothing is decoded), or None
    when it isn't known (e.g. a live stream) or the source can't be opened."""
    cmd = ["ffmpeg", "-nostdin", "-hide_banner", *_header_args(headers), "-i", source]
    try:
        # Without an output ffmpeg exits with an error, after printing the input's details.
        proc = subprocess.run(cmd, capture_output=True, check=False, timeout=PROBE_TIMEOUT_S)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    match = _DURATION.search(proc.stderr.decode(errors="replace"))
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
