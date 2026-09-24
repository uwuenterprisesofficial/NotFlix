import subprocess

import numpy as np

SAMPLE_RATE = 5512


class AudioDecodeError(RuntimeError):
    pass


def load_audio(source: str, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Decode any ffmpeg-readable file or URL into mono float32 PCM."""
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error",
        "-i", source,
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
