from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ListStatus(StrEnum):
    watching = "watching"
    completed = "completed"
    on_hold = "on_hold"
    dropped = "dropped"
    plan_to_watch = "plan_to_watch"


class SegmentKind(StrEnum):
    opening = "opening"
    ending = "ending"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    mal_user_id: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(String(100))
    picture: Mapped[str | None] = mapped_column(Text)
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str] = mapped_column(Text)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Anime(Base):
    """Local cache of MyAnimeList anime metadata; the primary key is the MAL anime id."""

    __tablename__ = "anime"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text)
    synopsis: Mapped[str | None] = mapped_column(Text)
    picture_url: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str | None] = mapped_column(String(30))
    num_episodes: Mapped[int | None] = mapped_column(Integer)
    mean: Mapped[float | None] = mapped_column(Float)
    popularity: Mapped[int | None] = mapped_column(Integer)
    genres: Mapped[list[str]] = mapped_column(JSON, default=list)
    start_season: Mapped[str | None] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ListEntry(Base):
    """One row of a user's MyAnimeList list (watch status and progress)."""

    __tablename__ = "list_entries"
    __table_args__ = (UniqueConstraint("user_id", "anime_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    anime_id: Mapped[int] = mapped_column(ForeignKey("anime.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))
    score: Mapped[int] = mapped_column(Integer, default=0)
    episodes_watched: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Recommendation(Base):
    """Precomputed on list sync so the browse page doesn't hit MAL for every request."""

    __tablename__ = "recommendations"
    __table_args__ = (UniqueConstraint("user_id", "anime_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    anime_id: Mapped[int] = mapped_column(ForeignKey("anime.id", ondelete="CASCADE"))
    score: Mapped[float] = mapped_column(Float)
    reason: Mapped[str | None] = mapped_column(Text)


class StreamSource(Base):
    """A playable source for one episode: an iframe embed page or a direct media URL."""

    __tablename__ = "stream_sources"
    __table_args__ = (UniqueConstraint("anime_id", "episode", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    episode: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(50))
    kind: Mapped[str] = mapped_column(String(10))  # "embed" | "direct"
    url: Mapped[str] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(10))  # e.g. "de-dub", "en-sub"


class EpisodeSource(Base):
    """A cached source option for one episode, as found by a provider scan."""

    __tablename__ = "episode_sources"
    __table_args__ = (UniqueConstraint("anime_id", "episode", "option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    episode: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(20))
    option_id: Mapped[str] = mapped_column(Text)
    label: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(10))
    resolved: Mapped[dict | None] = mapped_column(JSON)  # set when no /resolve call is needed
    position: Mapped[int] = mapped_column(Integer, default=0)


class ResolvedSource(Base):
    """The playable streams a source option resolved to, kept until its links likely expire."""

    __tablename__ = "resolved_sources"
    __table_args__ = (UniqueConstraint("anime_id", "episode", "option_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    episode: Mapped[int] = mapped_column(Integer)
    option_id: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON)
    resolved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceScan(Base):
    """Which episodes of an anime a provider was last checked for, and how that went."""

    __tablename__ = "source_scans"
    __table_args__ = (UniqueConstraint("anime_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    provider: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10))  # running | done | failed
    episodes: Mapped[list[int]] = mapped_column(JSON, default=list)  # covered by stored rows
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProviderMapping(Base):
    """How a MAL anime is identified on another service (AniList id, AniWorld slug + season)."""

    __tablename__ = "provider_mappings"
    __table_args__ = (UniqueConstraint("anime_id", "provider"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    provider: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str | None] = mapped_column(Text)  # None = looked up, not found
    season: Mapped[int | None] = mapped_column(Integer)
    episode_offset: Mapped[int] = mapped_column(Integer, default=0)
    manual: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SkipSegment(Base):
    """Detected (or manually entered) opening/ending range of an episode, in seconds."""

    __tablename__ = "skip_segments"
    __table_args__ = (UniqueConstraint("anime_id", "episode", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    episode: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10))
    start_s: Mapped[float] = mapped_column(Float)
    end_s: Mapped[float] = mapped_column(Float)
    confidence: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="analysis")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EpisodeFingerprint(Base):
    """An analysed episode's audio fingerprint: matching a new episode against it needs no
    second download. `compared_with` lists the episodes it was matched against; non-empty means
    this episode's intro/outro search is done."""

    __tablename__ = "episode_fingerprints"
    __table_args__ = (UniqueConstraint("anime_id", "episode"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    episode: Mapped[int] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(10))  # of the stream it was made from
    hashes: Mapped[bytes] = mapped_column(LargeBinary)  # little-endian uint32 per frame
    valid: Mapped[bytes] = mapped_column(LargeBinary)  # np.packbits of the per-frame flags
    frames: Mapped[int] = mapped_column(Integer)
    hop_seconds: Mapped[float] = mapped_column(Float)
    compared_with: Mapped[list[int]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    episodes: Mapped[list[int]] = mapped_column(JSON)
    # Only direct streams in this language are analysed (any language when None).
    language: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default=JobStatus.queued)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
