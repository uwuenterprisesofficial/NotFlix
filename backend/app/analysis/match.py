"""Find stretches of audio that two episodes share (openings, endings, recurring bumpers)."""

from dataclasses import dataclass

import numpy as np

from app.analysis.fingerprint import Fingerprint

MAX_BUCKET = 20  # ignore hashes this common in episode B; they carry no alignment information
MIN_VOTES = 5
TOP_OFFSETS = 8
NMS_RADIUS = 5  # frames
SMOOTH_SECONDS = 3.0
MAX_BER = 0.35


@dataclass(frozen=True)
class SharedSegment:
    a_start: float
    a_end: float
    b_start: float
    b_end: float
    score: float  # 1.0 = bit-identical, 0.0 = no better than chance

    @property
    def duration(self) -> float:
        return self.a_end - self.a_start


def _candidate_offsets(a: Fingerprint, b: Fingerprint) -> list[int]:
    """Vote for offsets d (frame i in A ~ frame i + d in B) using exact hash hits."""
    b_idx = np.flatnonzero(b.valid)
    a_idx = np.flatnonzero(a.valid)
    if len(a_idx) == 0 or len(b_idx) == 0:
        return []

    b_hashes = b.hashes[b_idx]
    order = np.argsort(b_hashes, kind="stable")
    b_sorted, b_pos = b_hashes[order], b_idx[order]

    a_hashes = a.hashes[a_idx]
    lo = np.searchsorted(b_sorted, a_hashes, "left")
    counts = np.searchsorted(b_sorted, a_hashes, "right") - lo
    keep = (counts > 0) & (counts <= MAX_BUCKET)
    if not keep.any():
        return []

    a_hit, lo, counts = a_idx[keep], lo[keep], counts[keep]
    within = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
    offsets = b_pos[np.repeat(lo, counts) + within] - np.repeat(a_hit, counts)

    shift = len(a)
    votes = np.bincount(offsets + shift, minlength=len(a) + len(b))
    result: list[int] = []
    for idx in np.argsort(votes)[::-1]:
        if votes[idx] < MIN_VOTES or len(result) >= TOP_OFFSETS:
            break
        offset = int(idx) - shift
        if all(abs(offset - o) > NMS_RADIUS for o in result):
            result.append(offset)
    return result


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    padded = np.concatenate(([False], mask, [False]))
    changes = np.flatnonzero(padded[1:] != padded[:-1])
    return list(zip(changes[::2].tolist(), changes[1::2].tolist(), strict=True))


def find_shared_segments(
    a: Fingerprint, b: Fingerprint, min_duration: float = 15.0
) -> list[SharedSegment]:
    hop = a.hop_seconds
    window = max(1, round(SMOOTH_SECONDS / hop))
    kernel = np.ones(window) / window
    segments: list[SharedSegment] = []

    for offset in _candidate_offsets(a, b):
        start_a = max(0, -offset)
        end_a = min(len(a), len(b) - offset)
        if end_a - start_a < window:
            continue
        a_slice = slice(start_a, end_a)
        b_slice = slice(start_a + offset, end_a + offset)

        ber = np.bitwise_count(a.hashes[a_slice] ^ b.hashes[b_slice]) / 32.0
        ber[~(a.valid[a_slice] & b.valid[b_slice])] = 0.5
        smoothed = np.convolve(ber, kernel, mode="same")

        for run_start, run_end in _runs(smoothed < MAX_BER):
            if (run_end - run_start) * hop < min_duration:
                continue
            i0, i1 = start_a + run_start, start_a + run_end
            if any(s.a_start <= i0 * hop < s.a_end for s in segments):
                continue
            mean_ber = float(ber[run_start:run_end].mean())
            segments.append(
                SharedSegment(
                    a_start=i0 * hop,
                    a_end=i1 * hop,
                    b_start=(i0 + offset) * hop,
                    b_end=(i1 + offset) * hop,
                    score=float(np.clip(1 - 2 * mean_ber, 0, 1)),
                )
            )
    return sorted(segments, key=lambda s: s.a_start)
