"""Robust audio fingerprints (Haitsma & Kalker, 2002).

Each frame is reduced to a 32-bit hash: bit m is the sign of the change, relative to the previous
frame, of the energy difference between bands m and m+1. Re-encoded copies of the same audio keep
most bits (bit error rate ~0.1-0.2), unrelated audio flips about half of them (~0.5).
"""

from dataclasses import dataclass

import numpy as np

from app.analysis.audio import SAMPLE_RATE

FRAME_SIZE = 2048  # ~0.37 s at 5512 Hz
HOP_SECONDS = 0.1
NUM_BANDS = 33
MIN_FREQ = 300.0
MAX_FREQ = 2000.0
_CHUNK_FRAMES = 2048


@dataclass(frozen=True)
class Fingerprint:
    hashes: np.ndarray  # uint32, one per frame
    valid: np.ndarray  # bool, False for (near-)silent frames whose bits are meaningless
    hop_seconds: float

    def __len__(self) -> int:
        return len(self.hashes)

    @property
    def duration(self) -> float:
        return len(self.hashes) * self.hop_seconds


def _band_edges(sample_rate: int) -> np.ndarray:
    freqs = np.geomspace(MIN_FREQ, MAX_FREQ, NUM_BANDS + 1)
    return np.round(freqs / sample_rate * FRAME_SIZE).astype(int)


def _band_energies(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    hop = round(sample_rate * HOP_SECONDS)
    n_frames = 1 + (len(samples) - FRAME_SIZE) // hop
    if n_frames <= 1:
        return np.zeros((0, NUM_BANDS), dtype=np.float64)

    window = np.hanning(FRAME_SIZE).astype(np.float32)
    edges = _band_edges(sample_rate)
    frames = np.lib.stride_tricks.sliding_window_view(samples, FRAME_SIZE)[::hop][:n_frames]

    energies = np.empty((n_frames, NUM_BANDS), dtype=np.float64)
    for start in range(0, n_frames, _CHUNK_FRAMES):
        chunk = frames[start : start + _CHUNK_FRAMES] * window
        power = np.abs(np.fft.rfft(chunk, axis=1)) ** 2
        cumulative = np.cumsum(power, axis=1)
        energies[start : start + len(chunk)] = (
            cumulative[:, edges[1:] - 1] - cumulative[:, edges[:-1] - 1]
        )
    return energies


def fingerprint(samples: np.ndarray, sample_rate: int = SAMPLE_RATE) -> Fingerprint:
    energies = _band_energies(np.asarray(samples, dtype=np.float32), sample_rate)
    if len(energies) < 2:
        return Fingerprint(np.zeros(0, np.uint32), np.zeros(0, bool), HOP_SECONDS)

    band_diff = energies[:, :-1] - energies[:, 1:]
    bits = (band_diff[1:] - band_diff[:-1]) > 0
    weights = (1 << np.arange(NUM_BANDS - 1, dtype=np.uint64)).astype(np.uint64)
    hashes = (bits.astype(np.uint64) * weights).sum(axis=1).astype(np.uint32)

    frame_energy = energies[1:].sum(axis=1)
    loud = frame_energy[frame_energy > 0]
    threshold = np.median(loud) * 1e-3 if len(loud) else np.inf
    valid = frame_energy > threshold

    return Fingerprint(hashes=hashes, valid=valid, hop_seconds=HOP_SECONDS)
