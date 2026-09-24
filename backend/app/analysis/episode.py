"""One episode's audio, decoded in parts on demand."""

import logging

import numpy as np

from app.analysis.audio import SAMPLE_RATE, AudioDecodeError, load_audio, probe_duration
from app.analysis.fingerprint import Fingerprint, fingerprint
from app.analysis.media import Media, resolve_all

log = logging.getLogger(__name__)


class EpisodeAudio:
    """Decodes an episode (or parts of it) from the first of its links that plays, and keeps
    using that one. Stored links may have expired: if none plays, fresh ones are fetched once
    (`fresh` starts with those)."""

    def __init__(self, anime_id: int, episode: int, language: str | None, fresh: bool = False):
        self.anime_id, self.episode, self.language = anime_id, episode, language
        self._fresh = fresh
        self._links: list[Media] | None = None
        self._working: Media | None = None
        self.decoded_s = 0.0  # how much audio was decoded, for the log

    def _candidates(self) -> list[Media]:
        if self._links is None:
            self._links = resolve_all(self.anime_id, [self.episode], self.language, self._fresh)[
                self.episode
            ]
        return self._links

    def _refresh(self) -> bool:
        """Switch to fresh links; False when they already are."""
        if self._fresh:
            return False
        self._fresh, self._links, self._working = True, None, None
        return True

    def _decode(self, start_s: float | None = None, duration_s: float | None = None) -> np.ndarray:
        if self._working:
            try:
                return load_audio(
                    self._working.source,
                    self._working.headers,
                    start_s=start_s,
                    duration_s=duration_s,
                )
            except AudioDecodeError:
                self._working = None  # the link stopped working; look for another one
        error: AudioDecodeError | None = None
        while True:
            for media in self._candidates():
                try:
                    audio = load_audio(
                        media.source, media.headers, start_s=start_s, duration_s=duration_s
                    )
                except AudioDecodeError as e:
                    log.warning(
                        "Episode %s: %s failed to decode: %s", self.episode, media.source, e
                    )
                    error = e
                    continue
                self._working = media
                return audio
            if not self._refresh():
                raise AudioDecodeError(
                    f"No stream of episode {self.episode} could be decoded: {error}"
                )

    def duration(self) -> float | None:
        """The episode's length from its header/playlist, or None if it can't be told."""
        for media in [self._working] if self._working else self._candidates():
            found = probe_duration(media.source, media.headers)
            if found:
                self._working = media
                return found
        return None

    def window(self, start_s: float, duration_s: float) -> Fingerprint:
        audio = self._decode(start_s, duration_s)
        self.decoded_s += duration_s
        return fingerprint(audio)

    def full(self) -> Fingerprint:
        audio = self._decode()
        self.decoded_s += len(audio) / SAMPLE_RATE
        return fingerprint(audio)
