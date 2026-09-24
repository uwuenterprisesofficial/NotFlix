import logging
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.audio import AudioDecodeError, load_audio
from app.analysis.detect import detect_segments
from app.analysis.fingerprint import Fingerprint, fingerprint
from app.analysis.media import Media, MediaNotFound, resolve_all
from app.analysis.store import load_fingerprints, save_fingerprint, to_fingerprint
from app.db.session import sync_session
from app.models import AnalysisJob, JobStatus, SkipSegment

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


def run_analysis(job_id: str) -> None:
    """RQ entrypoint: find the openings/endings of the job's episodes and store them, together
    with each episode's fingerprint so later episodes can be matched without downloading these
    again."""
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
            if len(fingerprints) == 1:
                [episode] = fingerprints
                partner, fp = _partner(db, job.anime_id, episode, job.language, saved)
                fingerprints[partner] = fp

            detected = detect_segments(fingerprints)
            # Record who was compared with whom (neighbours in episode order).
            order = sorted(fingerprints)
            for i, episode in enumerate(order):
                neighbours = order[max(0, i - 1) : i] + order[i + 1 : i + 2]
                row = saved[episode]
                row.compared_with = sorted(set(row.compared_with or []) | set(neighbours))

            existing = {
                (s.episode, s.kind): s
                for s in db.scalars(
                    select(SkipSegment).where(
                        SkipSegment.anime_id == job.anime_id,
                        SkipSegment.episode.in_(list(fingerprints)),
                    )
                )
            }
            for episode, segments in detected.items():
                for seg in segments:
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
