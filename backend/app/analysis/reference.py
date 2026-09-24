"""Find a known opening/ending (a saved fingerprint of just that part) inside an episode."""

from collections.abc import Callable
from dataclasses import dataclass, replace

import numpy as np

from app.analysis.fingerprint import Fingerprint
from app.analysis.match import MAX_BER, SMOOTH_SECONDS, runs

# How much of the reference must be found: openings are sometimes shortened, rarely by half.
MIN_MATCH_SHARE = 0.5
MIN_MATCH_SECONDS = 10.0
CANDIDATES = 3  # best offsets examined closely
CANDIDATE_BER = 0.45  # unrelated audio averages 0.5
EDGE_BLUR_SECONDS = 5.0
_CHUNK = 2048


@dataclass(frozen=True)
class Located:
    start_s: float
    end_s: float
    confidence: float


def cut(fp: Fingerprint, start_s: float, end_s: float) -> Fingerprint:
    """The part of a fingerprint between two times: what's saved as a reference."""
    i0, i1 = round(start_s / fp.hop_seconds), round(end_s / fp.hop_seconds)
    return Fingerprint(fp.hashes[i0:i1].copy(), fp.valid[i0:i1].copy(), fp.hop_seconds)


def _offset_ber(episode: Fingerprint, reference: Fingerprint, pad: int) -> np.ndarray:
    """Mean bit error rate of the reference laid over the episode at every offset (the episode
    padded by `pad` unknown frames on both sides, so a reference may stick out by that much).
    Unlike hash voting this needs no bit-exact frames, so it also finds a part that sits between
    two frames of the episode's grid (bit errors ~0.2-0.3 instead of ~0.1)."""
    hashes = np.concatenate([np.zeros(pad, np.uint32), episode.hashes, np.zeros(pad, np.uint32)])
    valid = np.concatenate([np.zeros(pad, bool), episode.valid, np.zeros(pad, bool)])
    n = len(reference)
    view_h = np.lib.stride_tricks.sliding_window_view(hashes, n)
    view_v = np.lib.stride_tricks.sliding_window_view(valid, n)
    out = np.empty(len(view_h))
    for i in range(0, len(view_h), _CHUNK):
        ber = np.bitwise_count(view_h[i : i + _CHUNK] ^ reference.hashes) / 32.0
        ber[~(view_v[i : i + _CHUNK] & reference.valid)] = 0.5
        out[i : i + _CHUNK] = ber.mean(axis=1)
    return out


def _frame_ber(episode: Fingerprint, reference: Fingerprint, start: int) -> np.ndarray:
    """Per-frame bit error rate of the reference placed at episode frame `start` (may be < 0)."""
    n = len(reference)
    ber = np.full(n, 0.5)
    lo, hi = max(0, -start), min(n, len(episode) - start)
    if hi > lo:
        e = slice(start + lo, start + hi)
        ber[lo:hi] = np.bitwise_count(episode.hashes[e] ^ reference.hashes[lo:hi]) / 32.0
        ber[lo:hi][~(episode.valid[e] & reference.valid[lo:hi])] = 0.5
    return ber


def locate(episode: Fingerprint, reference: Fingerprint) -> Located | None:
    """Where the reference plays in the episode. The reference is slid over the episode; at the
    best offsets the longest stretch whose (smoothed) bit error rate stays low is the match.
    Its edges are blurred by the smoothing, so they're widened to the reference's own start/end
    when that's within the blur; a genuinely shortened opening keeps its shorter length."""
    hop = reference.hop_seconds
    n = len(reference)
    min_frames = round(max(MIN_MATCH_SECONDS, MIN_MATCH_SHARE * reference.duration) / hop)
    if n < min_frames or len(episode) < min_frames:
        return None
    pad = n - min_frames
    mean_ber = _offset_ber(episode, reference, pad)

    window = max(1, round(SMOOTH_SECONDS / hop))
    kernel = np.ones(window) / window
    edge = round(EDGE_BLUR_SECONDS / hop)
    best: tuple[int, float, int, int] | None = None  # (frames, score, start frame, end frame)
    tried: list[int] = []
    for offset in np.argsort(mean_ber)[: CANDIDATES * 8]:
        if len(tried) >= CANDIDATES or mean_ber[offset] > CANDIDATE_BER:
            break
        if any(abs(int(offset) - t) < n // 2 for t in tried):
            continue
        tried.append(int(offset))
        start = int(offset) - pad  # the reference's first frame, in episode frames
        ber = _frame_ber(episode, reference, start)
        smoothed = np.convolve(ber, kernel, mode="same")
        for r0, r1 in runs(smoothed < MAX_BER):
            if r1 - r0 < min_frames:
                continue
            score = float(np.clip(1 - 2 * ber[r0:r1].mean(), 0, 1))
            if best is None or (r1 - r0, score) > best[:2]:
                a = 0 if r0 <= edge else r0
                b = n if n - r1 <= edge else r1
                best = (r1 - r0, score, start + a, start + b)
    if best is None:
        return None
    _, score, first, last = best
    return Located(max(0.0, first * hop), min(episode.duration, last * hop), score)


# Openings are searched from the start and endings from the end, this much at a time (plus the
# reference's length, so one playing across a window's edge is still whole in the next).
WINDOW_S = 180.0
EDGE_S = 10.0


def _best(fp: Fingerprint, references: list[Fingerprint], offset_s: float) -> Located | None:
    hits = [hit for ref in references if (hit := locate(fp, ref))]
    if not hits:
        return None
    best = max(hits, key=lambda h: h.confidence)
    return replace(best, start_s=best.start_s + offset_s, end_s=best.end_s + offset_s)


def search_windows(
    window: Callable[[float, float], Fingerprint],
    duration: float,
    references: dict[str, list[Fingerprint]],
) -> dict[str, Located]:
    """Find the saved openings/endings by decoding only where they play: openings window by
    window from the start (up to the middle), endings window by window from the end backwards
    (down to the opening, or the middle). A kind without saved references isn't searched.
    `window(start, length)` fingerprints that part of the episode."""
    found: dict[str, Located] = {}
    openings = references.get("opening", [])
    if openings:
        length = WINDOW_S + max(r.duration for r in openings) + EDGE_S
        start = 0.0
        while start < duration / 2:
            hit = _best(window(start, min(length, duration - start)), openings, start)
            if hit:
                found["opening"] = hit
                break
            start += WINDOW_S

    endings = references.get("ending", [])
    if endings:
        floor = found["opening"].end_s if "opening" in found else duration / 2
        length = WINDOW_S + max(r.duration for r in endings) + EDGE_S
        end = duration
        while end > floor:
            start = max(floor, end - length)
            hit = _best(window(start, end - start), endings, start)
            if hit:
                found["ending"] = hit
                break
            end -= WINDOW_S
    return found
