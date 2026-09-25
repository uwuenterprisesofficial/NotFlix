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
    false,
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
    """A NotFlix user, signed in with MyAnimeList, AniList or both (linked accounts), or a guest
    (Watch Together without a list: joined through an invite link, with just a name)."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    picture: Mapped[str | None] = mapped_column(Text)
    # MyAnimeList account (the column names predate AniList support).
    mal_user_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    mal_name: Mapped[str | None] = mapped_column(String(100))
    access_token: Mapped[str | None] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # AniList account. Its tokens last a year and can't be refreshed.
    anilist_user_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    anilist_name: Mapped[str | None] = mapped_column(String(100))
    anilist_token: Mapped[str | None] = mapped_column(Text)
    anilist_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_guest: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def has_mal(self) -> bool:
        return self.mal_user_id is not None and self.access_token is not None

    @property
    def has_anilist(self) -> bool:
        return self.anilist_user_id is not None and self.anilist_token is not None


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
    # Genres, themes and demographics with their MAL ids ([{"id": 1, "name": "Action"}]).
    genre_tags: Mapped[list[dict]] = mapped_column(JSON, default=list, server_default="[]")
    studios: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    source: Mapped[str | None] = mapped_column(String(30))  # e.g. manga, light_novel, original
    rating: Mapped[str | None] = mapped_column(String(10))  # e.g. pg_13, r
    num_list_users: Mapped[int | None] = mapped_column(Integer)
    num_scoring_users: Mapped[int | None] = mapped_column(Integer)
    rank: Mapped[int | None] = mapped_column(Integer)
    average_episode_duration: Mapped[int | None] = mapped_column(Integer)  # seconds
    start_year: Mapped[int | None] = mapped_column(Integer)
    # Synonyms, English and Japanese titles, for searching the catalogue.
    alt_titles: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    # When MAL's own data was last stored (None: only another source's so far, e.g. AniList).
    mal_details_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Airing: the next episode and when it airs (AniList's schedule), checked at airing_checked_at.
    next_episode: Mapped[int | None] = mapped_column(Integer)
    next_episode_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    airing_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # When the catalogue worker last completed the entry (MAL details, translated synopses).
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class AnimeSynopsis(Base):
    """A show's synopsis in another language than MAL's English (e.g. German from AniWorld).
    `synopsis` is None when none was found; it's looked for again after a while."""

    __tablename__ = "anime_synopses"
    __table_args__ = (UniqueConstraint("anime_id", "language"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    language: Mapped[str] = mapped_column(String(5))
    synopsis: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(20))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AiringEpisode(Base):
    """One episode's (Japanese) air time, from AniList's airing schedule."""

    __tablename__ = "airing_schedule"
    __table_args__ = (UniqueConstraint("anime_id", "episode"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)  # MAL id
    episode: Mapped[int] = mapped_column(Integer)
    airing_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PlaybackPosition(Base):
    """Where the user stopped in the episode they're watching of a show (one per show), to
    resume from there on any device signed in with the same MAL/AniList account."""

    __tablename__ = "playback_positions"
    __table_args__ = (UniqueConstraint("user_id", "anime_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    anime_id: Mapped[int] = mapped_column(Integer)
    episode: Mapped[int] = mapped_column(Integer)
    position_s: Mapped[float] = mapped_column(Float)
    duration_s: Mapped[float | None] = mapped_column(Float)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Connection(Base):
    """Two users who watch together: joint recommendations and a synced player (Watch
    Together). Stored once per pair, with the lower user id first."""

    __tablename__ = "connections"
    __table_args__ = (UniqueConstraint("user_a_id", "user_b_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_b_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def partner_of(self, user_id: int) -> int:
        return self.user_b_id if user_id == self.user_a_id else self.user_a_id


class ConnectionInvite(Base):
    """A link one user sends another to connect (Watch Together). Used once."""

    __tablename__ = "connection_invites"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TasteModel(Base):
    """A user's fitted score predictor (see services.taste), refitted on every list sync."""

    __tablename__ = "taste_models"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    data: Mapped[dict] = mapped_column(JSON)
    fitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class StreamFailure(Base):
    """A stream that wouldn't play (a source's server for one episode), so the player tries the
    others first next time. Cleared when it plays again."""

    __tablename__ = "stream_failures"
    __table_args__ = (UniqueConstraint("anime_id", "episode", "option_id", "stream"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    episode: Mapped[int] = mapped_column(Integer)
    option_id: Mapped[str] = mapped_column(String(200))
    stream: Mapped[str] = mapped_column(String(100))  # the stream's label (server/hoster)
    count: Mapped[int] = mapped_column(Integer, default=1)
    failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


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


class ReferenceSegment(Base):
    """A show's opening or ending as a fingerprint, cut from an episode where comparing two
    episodes found it. Later episodes are searched for it directly. A show can have several
    per kind (e.g. a new opening in the second cour)."""

    __tablename__ = "reference_segments"
    __table_args__ = (UniqueConstraint("anime_id", "kind", "source_episode"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(10))
    source_episode: Mapped[int] = mapped_column(Integer)
    hashes: Mapped[bytes] = mapped_column(LargeBinary)
    valid: Mapped[bytes] = mapped_column(LargeBinary)
    frames: Mapped[int] = mapped_column(Integer)
    hop_seconds: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalysisJob(Base):
    __tablename__ = "analysis_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    anime_id: Mapped[int] = mapped_column(Integer, index=True)
    episodes: Mapped[list[int]] = mapped_column(JSON)
    # Only direct streams in this language are analysed (any language when None).
    language: Mapped[str | None] = mapped_column(String(10))
    # Compare episodes even where saved opening/ending fingerprints could be searched for.
    compare: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Download the episodes again (fresh links) instead of using their saved fingerprints.
    redownload: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    status: Mapped[str] = mapped_column(String(10), default=JobStatus.queued)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
