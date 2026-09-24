"""Saved fingerprints: an episode analysed once never has to be downloaded again to be matched."""

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.fingerprint import Fingerprint
from app.models import EpisodeFingerprint


def to_fingerprint(row: EpisodeFingerprint) -> Fingerprint:
    hashes = np.frombuffer(row.hashes, dtype="<u4").astype(np.uint32)
    valid = np.unpackbits(np.frombuffer(row.valid, dtype=np.uint8), count=row.frames).astype(bool)
    return Fingerprint(hashes=hashes, valid=valid, hop_seconds=row.hop_seconds)


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
    row.hashes = fp.hashes.astype("<u4").tobytes()
    row.valid = np.packbits(fp.valid).tobytes()
    row.frames = len(fp.hashes)
    row.hop_seconds = fp.hop_seconds
    return row
