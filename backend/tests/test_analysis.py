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


def _noise(rng, seconds: float) -> np.ndarray:
    return rng.standard_normal(round(seconds * SAMPLE_RATE)).astype(np.float32)


def test_locate_finds_a_reference_between_frames():
    """A saved opening sitting half a frame off the episode's fingerprint grid shares no exact
    hashes with it; the sliding search still finds it, with its edges."""
    from app.analysis.reference import cut, locate

    rng = np.random.default_rng(7)
    opening = _noise(rng, 60)
    first = fingerprint(np.concatenate([_noise(rng, 10), opening, _noise(rng, 300)]))
    reference = cut(first, 10, 70)
    # 37.05 s: half of the 0.1 s hop away from the grid the reference was cut on.
    episode = fingerprint(np.concatenate([_noise(rng, 37.05), opening, _noise(rng, 500)]))

    hit = locate(episode, reference)
    assert hit is not None
    assert hit.start_s == pytest.approx(37.05, abs=0.3)
    assert hit.end_s == pytest.approx(97.05, abs=0.3)
    assert locate(fingerprint(_noise(rng, 400)), reference) is None  # unrelated audio


def test_locate_keeps_a_shortened_opening_short():
    from app.analysis.reference import cut, locate

    rng = np.random.default_rng(8)
    opening = _noise(rng, 90)
    reference = cut(fingerprint(np.concatenate([_noise(rng, 5), opening, _noise(rng, 60)])), 5, 95)
    # Only the first 60 s of the opening, straight into the episode.
    episode = fingerprint(
        np.concatenate([_noise(rng, 20), opening[: 60 * SAMPLE_RATE], _noise(rng, 600)])
    )

    hit = locate(episode, reference)
    assert hit.start_s == pytest.approx(20, abs=0.5)
    assert hit.end_s == pytest.approx(80, abs=3.5)  # not widened to the reference's 90 s


def test_search_windows_reads_the_opening_from_the_start_and_the_ending_from_the_end():
    from app.analysis.reference import cut, search_windows

    rng = np.random.default_rng(9)
    opening, ending = _noise(rng, 80), _noise(rng, 80)
    source = np.concatenate([_noise(rng, 30), opening, _noise(rng, 1100), ending, _noise(rng, 60)])
    saved = fingerprint(source)
    references = {"opening": [cut(saved, 30, 110)], "ending": [cut(saved, 1210, 1290)]}
    episode = np.concatenate([_noise(rng, 45), opening, _noise(rng, 1150), ending, _noise(rng, 45)])
    duration = len(episode) / SAMPLE_RATE
    windows = []

    def window(start, length):
        windows.append((start, length))
        return fingerprint(
            episode[round(start * SAMPLE_RATE) : round((start + length) * SAMPLE_RATE)]
        )

    found = search_windows(window, duration, references)
    assert found["opening"].start_s == pytest.approx(45, abs=0.5)
    assert found["ending"].start_s == pytest.approx(1275, abs=0.5)
    # Two windows: one from the start, one ending at the end; most of the episode unread.
    [(head, head_len), (tail, tail_len)] = windows
    assert head == 0 and tail + tail_len == pytest.approx(duration)
    assert head_len + tail_len < 0.4 * duration

    windows.clear()
    assert set(search_windows(window, duration, {"opening": references["opening"]})) == {"opening"}
    assert len(windows) == 1  # no saved ending: done after the opening


def test_comparing_finds_parts_that_sit_between_frames():
    """Two episodes whose opening/ending sit half a frame apart on their fingerprint grids
    share almost no bit-exact hashes; comparing still finds both."""
    rng = np.random.default_rng(11)
    opening, ending = _noise(rng, 85), _noise(rng, 88)
    a = np.concatenate([_noise(rng, 12.0), opening, _noise(rng, 900), ending, _noise(rng, 40)])
    b = np.concatenate([_noise(rng, 47.05), opening, _noise(rng, 870), ending, _noise(rng, 25)])
    fa, fb = fingerprint(a), fingerprint(b)
    shared_hashes = len(np.intersect1d(fa.hashes, fb.hashes))
    assert shared_hashes < 50  # of ~1700 frames of shared audio

    found = detect_segments({1: fa, 2: fb})
    by_kind = {ep: {s.kind: s for s in segs} for ep, segs in found.items()}
    assert by_kind[1][SegmentKind.opening].start_s == pytest.approx(12.0, abs=1.5)
    assert by_kind[2][SegmentKind.opening].start_s == pytest.approx(47.05, abs=1.5)
    assert by_kind[1][SegmentKind.ending].start_s == pytest.approx(997, abs=1.5)
    assert by_kind[2][SegmentKind.ending].start_s == pytest.approx(1002.05, abs=1.5)


def test_shared_silence_is_not_a_match():
    rng = np.random.default_rng(12)
    silence = np.zeros(40 * SAMPLE_RATE, np.float32)
    a = np.concatenate([_noise(rng, 100), silence, _noise(rng, 300)])
    b = np.concatenate([_noise(rng, 250), silence, _noise(rng, 150)])
    assert find_shared_segments(fingerprint(a), fingerprint(b)) == []
