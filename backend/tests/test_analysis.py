import numpy as np
import pytest

from app.analysis.audio import SAMPLE_RATE
from app.analysis.detect import detect_segments
from app.analysis.fingerprint import fingerprint
from app.analysis.match import find_shared_segments
from app.models import SegmentKind

SR = SAMPLE_RATE
TOLERANCE_S = 1.5


def _noise(rng: np.random.Generator, seconds: float) -> np.ndarray:
    return rng.standard_normal(int(seconds * SR)).astype(np.float32) * 0.1


def _episode(rng, layout, shared):
    """layout: list of (kind, seconds) where kind is 'unique', 'silence' or a key of `shared`."""
    parts, marks, t = [], {}, 0.0
    for kind, seconds in layout:
        if kind == "unique":
            chunk = _noise(rng, seconds)
        elif kind == "silence":
            chunk = np.zeros(int(seconds * SR), np.float32)
        else:
            source = shared[kind]
            # Simulate a different encode: gain change plus low-level noise.
            chunk = source * 0.8 + rng.standard_normal(len(source)).astype(np.float32) * 0.005
            marks[kind] = (t, t + len(source) / SR)
        parts.append(chunk)
        t += len(chunk) / SR
    return np.concatenate(parts), marks


@pytest.fixture(scope="module")
def episodes():
    rng = np.random.default_rng(42)
    shared = {"op": _noise(rng, 90), "ed": _noise(rng, 85)}
    ep1, m1 = _episode(
        rng,
        [("unique", 40), ("op", 0), ("silence", 20), ("unique", 500), ("ed", 0), ("unique", 25)],
        shared,
    )
    ep2, m2 = _episode(
        rng,
        [("unique", 95), ("op", 0), ("unique", 450), ("silence", 20), ("ed", 0), ("unique", 10)],
        shared,
    )
    return {1: (fingerprint(ep1), m1), 2: (fingerprint(ep2), m2)}


def test_unrelated_audio_shares_nothing():
    rng = np.random.default_rng(7)
    a = fingerprint(_noise(rng, 120))
    b = fingerprint(_noise(rng, 120))
    assert find_shared_segments(a, b) == []


def test_finds_shared_segments_at_different_offsets(episodes):
    (fp1, m1), (fp2, m2) = episodes[1], episodes[2]
    found = find_shared_segments(fp1, fp2)
    assert len(found) == 2
    op, ed = found
    assert op.a_start == pytest.approx(m1["op"][0], abs=TOLERANCE_S)
    assert op.b_start == pytest.approx(m2["op"][0], abs=TOLERANCE_S)
    assert op.a_end == pytest.approx(m1["op"][1], abs=TOLERANCE_S)
    assert ed.a_start == pytest.approx(m1["ed"][0], abs=TOLERANCE_S)
    assert ed.b_end == pytest.approx(m2["ed"][1], abs=TOLERANCE_S)
    assert op.score > 0.5


def test_detect_segments_labels_opening_and_ending(episodes):
    result = detect_segments({ep: fp for ep, (fp, _) in episodes.items()})
    for ep, (_, marks) in episodes.items():
        by_kind = {s.kind: s for s in result[ep]}
        assert set(by_kind) == {SegmentKind.opening, SegmentKind.ending}
        for kind, key in ((SegmentKind.opening, "op"), (SegmentKind.ending, "ed")):
            assert by_kind[kind].start_s == pytest.approx(marks[key][0], abs=TOLERANCE_S)
            assert by_kind[kind].end_s == pytest.approx(marks[key][1], abs=TOLERANCE_S)


def test_empty_audio():
    empty = fingerprint(np.zeros(100, np.float32))
    assert len(empty) == 0
    assert detect_segments({1: empty, 2: empty}) == {1: [], 2: []}
