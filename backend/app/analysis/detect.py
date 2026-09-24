"""Turn shared audio between episodes into per-episode opening/ending timestamps."""

from dataclasses import dataclass

from app.analysis.fingerprint import Fingerprint
from app.analysis.match import find_shared_segments
from app.models import SegmentKind

MIN_SEGMENT_SECONDS = 20.0
MAX_SEGMENT_SECONDS = 200.0


@dataclass(frozen=True)
class DetectedSegment:
    kind: SegmentKind
    start_s: float
    end_s: float
    confidence: float


def _classify(start: float, end: float, duration: float) -> SegmentKind | None:
    length = end - start
    if not MIN_SEGMENT_SECONDS <= length <= MAX_SEGMENT_SECONDS or duration <= 0:
        return None
    return SegmentKind.opening if (start + end) / 2 < duration / 2 else SegmentKind.ending


def detect_segments(fingerprints: dict[int, Fingerprint]) -> dict[int, list[DetectedSegment]]:
    """Compare each episode with the next one; keep the longest opening and ending per episode."""
    episodes = sorted(fingerprints)
    candidates: dict[int, list[DetectedSegment]] = {ep: [] for ep in episodes}

    for ep_a, ep_b in zip(episodes, episodes[1:], strict=False):
        fp_a, fp_b = fingerprints[ep_a], fingerprints[ep_b]
        for shared in find_shared_segments(fp_a, fp_b, min_duration=MIN_SEGMENT_SECONDS):
            for ep, fp, start, end in (
                (ep_a, fp_a, shared.a_start, shared.a_end),
                (ep_b, fp_b, shared.b_start, shared.b_end),
            ):
                kind = _classify(start, end, fp.duration)
                if kind:
                    candidates[ep].append(DetectedSegment(kind, start, end, shared.score))

    result: dict[int, list[DetectedSegment]] = {}
    for ep, found in candidates.items():
        best: dict[SegmentKind, DetectedSegment] = {}
        for seg in found:
            current = best.get(seg.kind)
            if current is None or (seg.end_s - seg.start_s, seg.confidence) > (
                current.end_s - current.start_s,
                current.confidence,
            ):
                best[seg.kind] = seg
        result[ep] = sorted(best.values(), key=lambda s: s.start_s)
    return result
