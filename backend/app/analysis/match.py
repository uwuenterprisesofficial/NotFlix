"""Find stretches of audio that two episodes share (openings, endings, recurring bumpers)."""

from dataclasses import dataclass

import numpy as np

from app.analysis.fingerprint import Fingerprint

TOP_OFFSETS = 8
SMOOTH_SECONDS = 3.0
MAX_BER = 0.35
# Offsets are found by sliding blocks of A over B: a block "is in B" where its bit error rate
# stays below BLOCK_MAX_BER (unrelated audio averages 0.5).
BLOCK_SECONDS = 10.0
BLOCK_MAX_BER = 0.35
MIN_BLOCK_VOTES = 2
CLUSTER_FRAMES = 3  # audio off each other's frame grid jitters by a frame
MAX_SILENT = 0.2  # silence hashes alike everywhere; mostly silent blocks/positions don't count


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
    """Offsets d (frame i in A ~ frame i + d in B) where A and B share audio, best first.

    Every 10 s block of A (in 5 s steps) is slid over B, computing its bit error rate at each
    position; a block that matches somewhere votes for that offset. Unlike looking up
    bit-exact hashes, this also finds shared audio that sits between the two episodes' frame
    grids (bit errors ~0.2-0.3 then, with hardly any exact hashes in common)."""
    n = max(1, round(BLOCK_SECONDS / a.hop_seconds))
    if len(a) < n or len(b) < n:
        return []
    view = np.lib.stride_tricks.sliding_window_view(b.hashes, n)
    silent_b = np.convolve(~b.valid, np.ones(n), mode="valid") / n > MAX_SILENT
    limit = BLOCK_MAX_BER * 32 * n
    votes: list[int] = []
    for start in range(0, len(a) - n + 1, max(1, n // 2)):
        if (~a.valid[start : start + n]).mean() > MAX_SILENT:
            continue
        errors = np.bitwise_count(view ^ a.hashes[start : start + n]).sum(axis=1, dtype=np.uint16)
        errors[silent_b] = 32 * n
        best = int(errors.argmin())
        if errors[best] < limit:
            votes.append(best - start)

    clusters: list[list[int]] = []
    for offset in sorted(votes):
        if clusters and offset - clusters[-1][-1] <= CLUSTER_FRAMES:
            clusters[-1].append(offset)
        else:
            clusters.append([offset])
    ranked = sorted((c for c in clusters if len(c) >= MIN_BLOCK_VOTES), key=len, reverse=True)
    return [int(np.median(c)) for c in ranked[:TOP_OFFSETS]]


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
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

        for run_start, run_end in runs(smoothed < MAX_BER):
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
