"""Saved fingerprints: of whole episodes (an episode analysed once never has to be downloaded
again to be compared) and of each show's openings/endings (searched for in new episodes)."""

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.fingerprint import Fingerprint
from app.models import EpisodeFingerprint, ReferenceSegment


def to_fingerprint(row: EpisodeFingerprint | ReferenceSegment) -> Fingerprint:
    hashes = np.frombuffer(row.hashes, dtype="<u4").astype(np.uint32)
    valid = np.unpackbits(np.frombuffer(row.valid, dtype=np.uint8), count=row.frames).astype(bool)
    return Fingerprint(hashes=hashes, valid=valid, hop_seconds=row.hop_seconds)


def _pack(row: EpisodeFingerprint | ReferenceSegment, fp: Fingerprint) -> None:
    row.hashes = fp.hashes.astype("<u4").tobytes()
    row.valid = np.packbits(fp.valid).tobytes()
    row.frames = len(fp.hashes)
    row.hop_seconds = fp.hop_seconds


def load_fingerprints(db: Session, anime_id: int) -> dict[int, EpisodeFingerprint]:
    rows = db.scalars(select(EpisodeFingerprint).where(EpisodeFingerprint.anime_id == anime_id))
    return {row.episode: row for row in rows}


def save_fingerprint(
    db: Session, anime_id: int, episode: int, language: str | None, fp: Fingerprint
) -> EpisodeFingerprint:
    row = db.scalar(
        select(EpisodeFingerprint).where(
            EpisodeFingerprint.anime_id == anime_id, EpisodeFingerprint.episode == episode
        )
    )
    if row is None:
        row = EpisodeFingerprint(anime_id=anime_id, episode=episode, compared_with=[])
        db.add(row)
    row.language = language
    _pack(row, fp)
    return row


def load_references(db: Session, anime_id: int) -> list[ReferenceSegment]:
    return list(
        db.scalars(
            select(ReferenceSegment)
            .where(ReferenceSegment.anime_id == anime_id)
            .order_by(ReferenceSegment.created_at.desc())
        )
    )


def save_reference(
    db: Session, anime_id: int, kind: str, source_episode: int, fp: Fingerprint
) -> ReferenceSegment:
    row = ReferenceSegment(anime_id=anime_id, kind=kind, source_episode=source_episode)
    _pack(row, fp)
    db.add(row)
    return row
