from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Progress(BaseModel):
    status: str
    episodes_watched: int
    score: int


class ReasonOut(BaseModel):
    name: str
    points: float  # how much this feature moves the predicted score


class PredictionOut(BaseModel):
    """The user's predicted score for a show they haven't scored (see services.taste)."""

    score: float
    tier: Literal["must_watch", "recommended", "maybe", "skip", "avoid"]
    reasons: list[ReasonOut] = []


class TagOut(BaseModel):
    id: int
    name: str
    category: Literal["genre", "explicit", "demographic", "theme"]


class AnimeCard(ORM):
    id: int
    title: str
    title_en: str | None = None
    picture_url: str | None = None
    media_type: str | None = None
    num_episodes: int | None = None
    mean: float | None = None
    genres: list[str] = []
    progress: Progress | None = None
    reason: str | None = None
    prediction: PredictionOut | None = None


class AnimeDetail(AnimeCard):
    synopsis: str | None = None
    status: str | None = None
    start_season: str | None = None
    tags: list[TagOut] = []
    studios: list[str] = []
    source: str | None = None
    rank: int | None = None
    num_list_users: int | None = None


class SearchResponse(BaseModel):
    items: list[AnimeCard]
    page: int
    has_next: bool
    source: Literal["mal", "jikan", "local"]  # where the results came from


class GenreOut(TagOut):
    count: int | None = None  # shows with it (from Jikan), when known


class ShowRefOut(BaseModel):
    id: int
    title: str
    title_en: str | None
    picture_url: str | None
    mean: float | None
    score: int | None  # the user's score
    prediction: PredictionOut | None


class StatusCountOut(BaseModel):
    status: str
    count: int


class OverviewOut(BaseModel):
    total: int
    by_status: list[StatusCountOut]
    episodes: int
    days: float | None
    scored: int
    mean_score: float | None
    median_score: float | None
    std_score: float | None
    mal_mean: float | None  # MAL's mean score of the shows the user scored
    mean_difference: float | None  # user score minus MAL mean, on average
    mean_abs_difference: float | None
    agreement: float | None  # correlation of the user's scores with MAL's
    median_members: int | None
    drop_rate: float | None


class ScoreBucketOut(BaseModel):
    score: int
    mine: int
    mal: int  # the user's scored shows whose MAL mean rounds to this score


class TagStatOut(BaseModel):
    key: str
    name: str
    kind: str  # genre | theme | demographic | explicit | studio | source | type | era
    count: int
    share: float
    scored: int
    mean_score: float | None
    mal_mean: float | None
    delta: float | None  # user score minus MAL mean on these shows
    affinity: float | None  # points above/below the user's own mean (shrunk for few shows)
    weight: float | None  # the prediction model's weight
    dropped: int


class HotTakeOut(BaseModel):
    kind: str
    title: str
    text: str
    value: float | None = None
    anime: ShowRefOut | None = None


class ModelFeatureOut(BaseModel):
    name: str
    kind: str
    points: float


class ModelStatsOut(BaseModel):
    scored: int
    mae: float | None  # cross-validated mean error of the predictions, in points
    baseline_mae: float | None  # the same for MAL's score shifted by the user's offset
    mal_weight: float | None
    thresholds: list[float]  # predicted score needed for must watch, recommended, maybe, skip
    likes: list[ModelFeatureOut]
    dislikes: list[ModelFeatureOut]


class StatsOut(BaseModel):
    overview: OverviewOut
    score_distribution: list[ScoreBucketOut]
    favourites: list[TagStatOut]
    hated: list[TagStatOut]
    breakdown: dict[str, list[TagStatOut]]
    hot_takes: list[HotTakeOut]
    model: ModelStatsOut | None
    plan_to_watch: list[ShowRefOut]


class Row(BaseModel):
    id: str
    title: str
    items: list[AnimeCard]


class BrowseResponse(BaseModel):
    hero: AnimeDetail | None
    rows: list[Row]
    signed_in: bool
    mal_configured: bool


class Me(ORM):
    id: int
    name: str
    picture: str | None
    last_synced_at: datetime | None


class SyncResult(BaseModel):
    entries: int
    recommendations: int


class SkipSegmentOut(ORM):
    kind: str
    start_s: float
    end_s: float
    confidence: float
    source: str


class EpisodeOut(BaseModel):
    anime_id: int
    episode: int
    skip_segments: list[SkipSegmentOut]


class SubtitleOut(BaseModel):
    url: str
    label: str
    lang: str | None


class StreamOut(BaseModel):
    kind: Literal["embed", "direct"]
    url: str
    label: str
    format: Literal["hls", "file"] | None
    subtitles: list[SubtitleOut]


class ResolvedOut(BaseModel):
    streams: list[StreamOut]
    skip_segments: list[SkipSegmentOut]
    # When these links were fetched, and until when they can be reused without resolving again.
    resolved_at: datetime | None = None
    expires_at: datetime | None = None


class SourceOptionOut(BaseModel):
    id: str
    provider: str
    label: str
    language: str
    resolved: ResolvedOut | None


class ProviderCoverageOut(BaseModel):
    name: str
    status: str  # done | running | failed | none (never scanned)
    episodes: list[int]  # episodes whose options are included


class EpisodeOptionsOut(BaseModel):
    episode: int
    options: list[SourceOptionOut]


class CachedResolutionOut(BaseModel):
    episode: int
    option: str
    resolved: ResolvedOut


class ShowStreamsOut(BaseModel):
    """Everything the player needs for a show, to keep in the browser until `expires_at`."""

    providers: list[ProviderCoverageOut]
    scanning: bool
    expires_at: datetime
    episodes: list[EpisodeOptionsOut]
    resolutions: list[CachedResolutionOut]


class ProviderScanOut(ORM):
    provider: str
    status: str
    error: str | None
    finished_at: datetime | None


class EpisodeLanguages(BaseModel):
    episode: int
    languages: list[str]


class AvailabilityOut(BaseModel):
    episodes: list[EpisodeLanguages]  # only episodes with at least one source
    checked: list[int]  # episodes every reachable provider has looked at
    scans: list[ProviderScanOut]
    scanning: bool


class MappingOut(ORM):
    provider: str
    external_id: str | None
    season: int | None
    episode_offset: int
    manual: bool


class AniWorldMappingIn(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=200)
    season: int = Field(ge=0, le=100)
    episode_offset: int = Field(default=0, ge=-2000, le=2000)


class AnimeToastMappingIn(BaseModel):
    """animetoast page slugs of one show, one per language (e.g. naruto-ger-dub)."""

    slugs: list[Annotated[str, Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=200)]] = Field(
        min_length=1, max_length=6
    )
    episode_offset: int = Field(default=0, ge=-2000, le=2000)


class ProgressUpdate(BaseModel):
    episodes_watched: int = Field(ge=0)


class AnalyzeRequest(BaseModel):
    """A manual analysis: always recalculates these episodes, replacing earlier results (but
    never manually entered times)."""

    episodes: list[int] = Field(min_length=1, max_length=50)
    # The language whose direct streams are analysed; any language when omitted.
    language: Literal["de-dub", "de-sub", "en-sub", "en-dub", "unknown"] | None = None
    compare: bool = False  # compare episodes instead of searching the saved fingerprints
    redownload: bool = False  # e.g. to retry an episode whose result is wrong

    @field_validator("episodes")
    @classmethod
    def distinct_positive(cls, value: list[int]) -> list[int]:
        episodes = sorted(set(value))
        if episodes[0] < 1:
            raise ValueError("episode numbers start at 1")
        return episodes


class JobOut(ORM):
    id: str
    anime_id: int
    episodes: list[int]
    language: str | None
    compare: bool
    redownload: bool
    status: str
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AutoAnalyzeRequest(BaseModel):
    episode: int = Field(ge=1)  # the episode being watched; it and the next one are analysed
    language: Literal["de-dub", "de-sub", "en-sub", "en-dub", "unknown"] | None = None


class EpisodeAnalysisOut(BaseModel):
    episode: int
    analysed: bool  # matched against another episode (found something or not)
    segments: list[SkipSegmentOut]


class ReferenceOut(BaseModel):
    id: int
    kind: str
    source_episode: int
    duration_s: float


class AnalysisOverview(BaseModel):
    episodes: list[EpisodeAnalysisOut]
    references: list[
        ReferenceOut
    ]  # saved opening/ending fingerprints new episodes are searched for
    running: list[JobOut]  # queued or running jobs


class AnalyzeResponse(BaseModel):
    cached: bool
    job: JobOut | None
