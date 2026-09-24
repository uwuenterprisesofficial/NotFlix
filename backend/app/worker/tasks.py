import logging
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.audio import AudioDecodeError, load_audio
from app.analysis.detect import DetectedSegment, detect_segments
from app.analysis.fingerprint import Fingerprint, fingerprint
from app.analysis.media import Media, MediaNotFound, resolve_all
from app.analysis.reference import cut, locate
from app.analysis.store import (
    load_fingerprints,
    load_references,
    save_fingerprint,
    save_reference,
    to_fingerprint,
)
from app.db.session import sync_session
from app.models import (
    AnalysisJob,
    EpisodeFingerprint,
    JobStatus,
    ReferenceSegment,
    SegmentKind,
    SkipSegment,
)

log = logging.getLogger(__name__)

# Episodes tried (in this order, relative to the one analysed) when a single episode has no
# saved fingerprint to be matched against.
PARTNER_OFFSETS = (1, -1, 2, -2)


def _first_decodable(episode: int, candidates: list[Media]) -> np.ndarray:
    """Audio of the first candidate that decodes; a hoster's direct link may be dead."""
    error: AudioDecodeError | None = None
    for media in candidates:
        try:
            return load_audio(media.source, media.headers)
        except AudioDecodeError as e:
            log.warning("Episode %s: %s failed to decode: %s", episode, media.source, e)
            error = e
    raise AudioDecodeError(f"No stream of episode {episode} could be decoded: {error}")


def _decode(anime_id: int, episode: int, language: str | None) -> Fingerprint:
    """Download and fingerprint one episode. Stored links may have expired: if none of them
    decodes, the episode's links are fetched fresh once."""
    log.info("Fingerprinting anime %s episode %s", anime_id, episode)
    try:
        audio = _first_decodable(episode, resolve_all(anime_id, [episode], language)[episode])
    except AudioDecodeError:
        fresh = resolve_all(anime_id, [episode], language, fresh=True)[episode]
        audio = _first_decodable(episode, fresh)
    return fingerprint(audio)


def _partner(
    db: Session, anime_id: int, episode: int, language: str | None, saved: dict
) -> tuple[int, Fingerprint]:
    """Something to match a lone episode against: the nearest saved fingerprint (no download),
    else a neighbouring episode, which is fingerprinted and saved too."""
    others = [ep for ep in saved if ep != episode]
    if others:
        nearest = min(others, key=lambda ep: (abs(ep - episode), ep < episode))
        return nearest, to_fingerprint(saved[nearest])
    error: Exception | None = None
    for offset in PARTNER_OFFSETS:
        candidate = episode + offset
        if candidate < 1:
            continue
        try:
            fp = _decode(anime_id, candidate, language)
        except (MediaNotFound, AudioDecodeError) as e:
            error = e
            continue
        saved[candidate] = save_fingerprint(db, anime_id, candidate, language, fp)
        db.commit()
        return candidate, fp
    raise MediaNotFound(f"No other episode to compare episode {episode} with: {error}")


def _match_references(
    fp: Fingerprint, references: list[tuple[ReferenceSegment, Fingerprint]]
) -> dict[str, DetectedSegment]:
    """The episode's opening/ending found by searching it for the saved ones."""
    found: dict[str, DetectedSegment] = {}
    for ref, ref_fp in references:
        hit = locate(fp, ref_fp)
        if hit and (ref.kind not in found or hit.confidence > found[ref.kind].confidence):
            found[ref.kind] = DetectedSegment(
                SegmentKind(ref.kind), hit.start_s, hit.end_s, hit.confidence
            )
    return found


def _compare(
    db: Session,
    job: AnalysisJob,
    episodes: list[int],
    fingerprints: dict[int, Fingerprint],
    saved: dict[int, EpisodeFingerprint],
) -> dict[int, list[DetectedSegment]]:
    """Compare episodes with each other (a lone one with the nearest saved episode) to find
    what they share. Needed the first time, and for what no saved reference matches."""
    compared = {ep: fingerprints[ep] for ep in episodes}
    if len(compared) == 1:
        [episode] = compared
        partner, fp = _partner(db, job.anime_id, episode, job.language, saved)
        compared[partner] = fingerprints[partner] = fp
    order = sorted(compared)
    for i, episode in enumerate(order):
        neighbours = order[max(0, i - 1) : i] + order[i + 1 : i + 2]
        row = saved[episode]
        row.compared_with = sorted(set(row.compared_with or []) | set(neighbours))
    return detect_segments(compared)


def _learn_references(
    db: Session,
    anime_id: int,
    detected: dict[int, list[DetectedSegment]],
    fingerprints: dict[int, Fingerprint],
    references: list[tuple[ReferenceSegment, Fingerprint]],
) -> None:
    """Save each newly found opening/ending (the most confident one per kind) as a reference,
    unless it's one that's already saved."""
    best: dict[str, tuple[int, DetectedSegment]] = {}
    for episode, segments in detected.items():
        for seg in segments:
            current = best.get(seg.kind)
            if current is None or seg.confidence > current[1].confidence:
                best[seg.kind] = (episode, seg)
    for kind, (episode, seg) in best.items():
        snippet = cut(fingerprints[episode], seg.start_s, seg.end_s)
        known = [ref_fp for ref, ref_fp in references if ref.kind == kind]
        if any(locate(snippet, ref_fp) for ref_fp in known):
            continue
        if any(ref.kind == kind and ref.source_episode == episode for ref, _ in references):
            continue
        log.info("Anime %s: saving the %s of episode %s as a reference", anime_id, kind, episode)
        row = save_reference(db, anime_id, kind, episode, snippet)
        references.append((row, snippet))


def run_analysis(job_id: str) -> None:
    """RQ entrypoint: find the openings/endings of the job's episodes and store them.

    Episodes are searched for the show's saved opening/ending fingerprints. Only what that
    doesn't find (every time on a show's first analysis) is found by comparing two episodes,
    and what's found that way is saved as a reference for the next episodes. Each episode's
    own fingerprint is saved too, so comparing never needs to download it again."""
    with sync_session() as db:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            return
        job.status = JobStatus.running
        db.commit()

        try:
            saved = load_fingerprints(db, job.anime_id)
            fingerprints: dict[int, Fingerprint] = {}
            for episode in job.episodes:
                if episode in saved:
                    fingerprints[episode] = to_fingerprint(saved[episode])
                else:
                    fingerprints[episode] = _decode(job.anime_id, episode, job.language)
                    saved[episode] = save_fingerprint(
                        db, job.anime_id, episode, job.language, fingerprints[episode]
                    )
                    db.commit()  # a download is kept even if a later step fails

            references = [(ref, to_fingerprint(ref)) for ref in load_references(db, job.anime_id)]
            found = {ep: _match_references(fingerprints[ep], references) for ep in job.episodes}
            kinds = {kind.value for kind in SegmentKind}
            unresolved = [ep for ep in job.episodes if set(found[ep]) != kinds]
            detected: dict[int, list[DetectedSegment]] = {}
            if unresolved:
                detected = _compare(db, job, unresolved, fingerprints, saved)
                _learn_references(db, job.anime_id, detected, fingerprints, references)
            for episode, segments in detected.items():
                for seg in segments:
                    found.setdefault(episode, {}).setdefault(seg.kind, seg)

            existing = {
                (s.episode, s.kind): s
                for s in db.scalars(
                    select(SkipSegment).where(
                        SkipSegment.anime_id == job.anime_id,
                        SkipSegment.episode.in_(list(found)),
                    )
                )
            }
            for episode, by_kind in found.items():
                for seg in by_kind.values():
                    row = existing.get((episode, seg.kind))
                    if row is not None and row.source == "manual":
                        continue
                    # A partner episode only gains what it didn't have; the job's own
                    # episodes are (re)calculated.
                    if row is not None and episode not in job.episodes:
                        continue
                    if row is None:
                        row = SkipSegment(anime_id=job.anime_id, episode=episode, kind=seg.kind)
                        db.add(row)
                    row.start_s = round(seg.start_s, 2)
                    row.end_s = round(seg.end_s, 2)
                    row.confidence = round(seg.confidence, 3)
                    row.source = "analysis"

            job.status = JobStatus.done
        except Exception as e:
            db.rollback()
            job = db.get(AnalysisJob, job_id)
            job.status = JobStatus.failed
            job.error = str(e)[:2000]
            log.exception("Analysis job %s failed", job_id)
        finally:
            job.finished_at = datetime.now(UTC)
            db.commit()
