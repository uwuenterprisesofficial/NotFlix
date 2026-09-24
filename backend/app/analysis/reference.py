"""Find a known opening/ending (a saved fingerprint of just that part) inside an episode."""

from dataclasses import dataclass

from app.analysis.fingerprint import Fingerprint
from app.analysis.match import find_shared_segments

# How much of the reference must be found: openings are sometimes shortened, rarely by half.
MIN_MATCH_SHARE = 0.5
MIN_MATCH_SECONDS = 10.0


@dataclass(frozen=True)
class Located:
    start_s: float
    end_s: float
    confidence: float


def cut(fp: Fingerprint, start_s: float, end_s: float) -> Fingerprint:
    """The part of a fingerprint between two times: what's saved as a reference."""
    i0, i1 = round(start_s / fp.hop_seconds), round(end_s / fp.hop_seconds)
    return Fingerprint(fp.hashes[i0:i1].copy(), fp.valid[i0:i1].copy(), fp.hop_seconds)


def locate(episode: Fingerprint, reference: Fingerprint) -> Located | None:
    """Where the reference plays in the episode. The matched stretch is widened by whatever of
    the reference's start and end didn't match (the edges are blurred by smoothing), within the
    episode's bounds."""
    min_duration = max(MIN_MATCH_SECONDS, MIN_MATCH_SHARE * reference.duration)
    shared = find_shared_segments(reference, episode, min_duration=min_duration)
    if not shared:
        return None
    best = max(shared, key=lambda s: (s.duration, s.score))
    start = max(0.0, best.b_start - best.a_start)
    end = min(episode.duration, best.b_end + (reference.duration - best.a_end))
    return Located(start, end, best.score)
