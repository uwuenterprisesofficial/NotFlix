import logging
from datetime import UTC, datetime

from rq.timeouts import JobTimeoutException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.analysis.audio import AudioDecodeError
from app.analysis.detect import DetectedSegment, detect_segments
from app.analysis.episode import EpisodeAudio
from app.analysis.fingerprint import Fingerprint
from app.analysis.media import MediaNotFound
from app.analysis.reference import cut, locate, search_windows
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
from app.worker.queue import timeout_message

log = logging.getLogger(__name__)

# Episodes tried (in this order, relative to the one analysed) when a single episode has no
# saved fingerprint to be matched against.
PARTNER_OFFSETS = (1, -1, 2, -2)


def _decode(anime_id: int, episode: int, language: str | None, fresh: bool = False) -> Fingerprint:
    """Download and fingerprint a whole episode."""
    log.info("Fingerprinting anime %s episode %s", anime_id, episode)
    return EpisodeAudio(anime_id, episode, language, fresh).full()


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


def _search(
    audio: EpisodeAudio, references: list[tuple[ReferenceSegment, Fingerprint]]
) -> tuple[dict[str, DetectedSegment], Fingerprint | None]:
    """Search a new episode for the saved openings/endings, decoding only the parts where they
    play (see search_windows). Returns what was found, and the whole episode's fingerprint if
    it had to be decoded after all (its length couldn't be told)."""
    duration = audio.duration()
    if duration is None:
        fp = audio.full()
        return _match_references(fp, references), fp
    by_kind: dict[str, list[Fingerprint]] = {}
    for ref, ref_fp in references:
        by_kind.setdefault(ref.kind, []).append(ref_fp)
    found = search_windows(audio.window, duration, by_kind)
    log.info(
        "Episode %s: searched %.0f of %.0f s for the saved opening/ending, found %s",
        audio.episode, audio.decoded_s, duration, sorted(found) or "nothing",
    )  # fmt: skip
    return {
        kind: DetectedSegment(SegmentKind(kind), hit.start_s, hit.end_s, hit.confidence)
        for kind, hit in found.items()
    }, None


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
        if job is None or job.status != JobStatus.queued:
            return  # e.g. stopped before a worker got to it
        job.status = JobStatus.running
        job.started_at = datetime.now(UTC)
        db.commit()

        try:
            saved = load_fingerprints(db, job.anime_id)
            references = [(ref, to_fingerprint(ref)) for ref in load_references(db, job.anime_id)]
            known_kinds = {ref.kind for ref, _ in references}
            fingerprints: dict[int, Fingerprint] = {}
            found: dict[int, dict[str, DetectedSegment]] = {}
            unresolved: list[int] = []

            def keep(episode: int, fp: Fingerprint) -> None:
                """A whole episode's fingerprint: used now and saved for later comparisons."""
                fingerprints[episode] = fp
                saved[episode] = save_fingerprint(db, job.anime_id, episode, job.language, fp)
                db.commit()  # a download is kept even if a later step fails

            for episode in job.episodes:
                use_saved = episode in saved and not job.redownload
                if job.compare or not references:
                    # Compare episodes: asked for, or nothing saved yet (a show's first time).
                    if use_saved:
                        fingerprints[episode] = to_fingerprint(saved[episode])
                    else:
                        keep(episode, _decode(job.anime_id, episode, job.language, job.redownload))
                    found[episode] = {}
                    unresolved.append(episode)
                    continue

                audio = None
                if use_saved:
                    fingerprints[episode] = to_fingerprint(saved[episode])
                    found[episode] = _match_references(fingerprints[episode], references)
                else:
                    audio = EpisodeAudio(job.anime_id, episode, job.language, job.redownload)
                    found[episode], whole = _search(audio, references)
                    if whole is not None:
                        keep(episode, whole)
                # A saved opening/ending that isn't found may have changed (e.g. a new opening
                # in the second cour): compare episodes to learn it. Kinds nothing is saved for
                # aren't looked for.
                if known_kinds - set(found[episode]):
                    if episode not in fingerprints:
                        keep(episode, audio.full())
                    unresolved.append(episode)

            detected: dict[int, list[DetectedSegment]] = {}
            if unresolved:
                detected = _compare(db, job, unresolved, fingerprints, saved)
                _learn_references(db, job.anime_id, detected, fingerprints, references)
            for episode, segments in detected.items():
                for seg in segments:
                    found.setdefault(episode, {}).setdefault(seg.kind, seg)

            # The job's episodes are recalculated: an earlier result that isn't found again
            # (e.g. a wrong outro) goes. Manually entered times always stay, and AniSkip's stay
            # until a detected time replaces them.
            db.execute(
                delete(SkipSegment).where(
                    SkipSegment.anime_id == job.anime_id,
                    SkipSegment.episode.in_(job.episodes),
                    # Entered by hand: kept. AniSkip's: kept until something replaces them.
                    SkipSegment.source.notin_(("manual", "aniskip")),
                )
            )
            db.flush()

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
                    # A partner episode only gains what it didn't have (AniSkip's stand-in
                    # counts as not having it); the job's own episodes are (re)calculated.
                    if row is not None and row.source != "aniskip" and episode not in job.episodes:
                        continue
                    if row is None:
                        row = SkipSegment(anime_id=job.anime_id, episode=episode, kind=seg.kind)
                        db.add(row)
                    row.start_s = round(seg.start_s, 2)
                    row.end_s = round(seg.end_s, 2)
                    row.confidence = round(seg.confidence, 3)
                    row.source = "analysis"

            job.status = JobStatus.done
        except JobTimeoutException:
            # RQ stops a job at its timeout (ANALYSIS_TIMEOUT_MINUTES) by raising this in it.
            db.rollback()
            job = db.get(AnalysisJob, job_id)
            job.status = JobStatus.failed
            job.error = timeout_message()
            log.warning("Analysis job %s timed out", job_id)
        except Exception as e:
            db.rollback()
            job = db.get(AnalysisJob, job_id)
            job.status = JobStatus.failed
            job.error = str(e)[:2000]
            log.exception("Analysis job %s failed", job_id)
        finally:
            job.finished_at = datetime.now(UTC)
            db.commit()
