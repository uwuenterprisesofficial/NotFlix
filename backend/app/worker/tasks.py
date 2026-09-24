import logging
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import select

from app.analysis.audio import AudioDecodeError, load_audio
from app.analysis.detect import detect_segments
from app.analysis.fingerprint import fingerprint
from app.analysis.media import Media, resolve_all
from app.db.session import sync_session
from app.models import AnalysisJob, JobStatus, SkipSegment

log = logging.getLogger(__name__)


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


def run_analysis(job_id: str) -> None:
    """RQ entrypoint: fingerprint the job's episodes and store detected openings/endings."""
    with sync_session() as db:
        job = db.get(AnalysisJob, job_id)
        if job is None:
            return
        job.status = JobStatus.running
        db.commit()

        try:
            fingerprints = {}
            for episode, candidates in resolve_all(
                job.anime_id, job.episodes, job.language
            ).items():
                log.info("Fingerprinting anime %s episode %s", job.anime_id, episode)
                fingerprints[episode] = fingerprint(_first_decodable(episode, candidates))

            detected = detect_segments(fingerprints)
            existing = {
                (s.episode, s.kind): s
                for s in db.scalars(
                    select(SkipSegment).where(
                        SkipSegment.anime_id == job.anime_id,
                        SkipSegment.episode.in_(job.episodes),
                    )
                )
            }
            for episode, segments in detected.items():
                for seg in segments:
                    row = existing.get((episode, seg.kind))
                    if row is not None and row.source == "manual":
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
            job.status = JobStatus.failed
            job.error = str(e)[:2000]
            log.exception("Analysis job %s failed", job_id)
        finally:
            job.finished_at = datetime.now(UTC)
            db.commit()
