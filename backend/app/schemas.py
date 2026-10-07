from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Progress(BaseModel):
    status: str
    episodes_watched: int
    score: int
    failed: list[str] = []  # linked lists ("mal", "anilist") the change couldn't be saved to


class ReasonOut(BaseModel):
    # tag:<id>, studio:<name>, source:<source>, type:<type>, era:<decade>, mal, popularity, or
    # franchise / recommended (the name is the related show's title)
    key: str
    name: str
    points: float  # how much this feature moves the predicted score


class PredictionOut(BaseModel):
    """The user's predicted score for a show they haven't scored (see services.taste)."""

    score: float
    tier: Literal["must_watch", "recommended", "maybe", "skip", "avoid"]
    reasons: list[ReasonOut] = []
    # GUILTY WATCH: rated low by the community, but in the categories the user watches most.
    guilty: bool = False


class TagOut(BaseModel):
    id: int
    name: str
    category: Literal["genre", "explicit", "demographic", "theme"]


class ResumeOut(ORM):
    """Where the user stopped in the episode they're watching."""

    episode: int
    position_s: float
    duration_s: float | None


class PositionIn(BaseModel):
    episode: int = Field(ge=1)
    position_s: float = Field(ge=0)
    duration_s: float | None = Field(default=None, gt=0)


class AiringOut(BaseModel):
    episode: int
    airing_at: datetime


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
    airing: AiringOut | None = None
    resume: ResumeOut | None = None  # signed in: where the user stopped in this show
    status: str | None = None  # finished_airing, currently_airing, not_yet_aired
    start_season: str | None = None
    next_episode: int | None = None  # when airing: the next episode and its air time
    next_episode_at: datetime | None = None  # in the release calendar / New Episodes: this episode
    pair: "PairOut | None" = None  # Watch Together: both users' side of the show
    # Dubs NotFlix has found streams of ("de-dub", "en-dub"; shows looked up before only).
    dubs: list[str] = []


class AnimeDetail(AnimeCard):
    synopsis: str | None = None
    synopsis_language: str = "en"  # MAL's are English; see GET /anime/{id}/synopsis
    # Episodes aired so far (None: no limit known, e.g. finished), and the next one's air time.
    aired_episodes: int | None = None
    status: str | None = None
    start_season: str | None = None
    tags: list[TagOut] = []
    studios: list[str] = []
    source: str | None = None
    rank: int | None = None
    num_list_users: int | None = None


class SynopsisOut(BaseModel):
    language: str  # the language of `synopsis`: the one asked for, else "en" (MAL's)
    synopsis: str | None


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
    """One hot take; the UI words it from `kind` and `params` (in the viewer's language)."""

    kind: str  # harsh, generous, agreement, underrated, overrated, dropped_acclaimed, ...
    params: dict[str, float | int | str | None] = {}
    value: float | None = None
    anime: ShowRefOut | None = None


class ModelFeatureOut(BaseModel):
    key: str
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


class LibraryResponse(BaseModel):
    """The My List page: the user's list in sections, and shows related to what they watched."""

    sections: list[Row]
    # Relations of some listed shows are still being fetched: ask again in a moment.
    related_pending: bool = False


class BrowseResponse(BaseModel):
    hero: AnimeDetail | None
    rows: list[Row]
    signed_in: bool
    mal_configured: bool
    anilist_configured: bool = False
    # The list is being imported in the background (right after the first sign-in).
    syncing: bool = False


class AccountOut(BaseModel):
    name: str | None


class ListWriteOut(BaseModel):
    done: int
    total: int
    failed: int


class Me(ORM):
    id: int
    name: str
    picture: str | None
    last_synced_at: datetime | None
    guest: bool = False  # Watch Together without a list
    admin: bool = False  # may open the admin page
    mal: AccountOut | None = None  # linked MyAnimeList account
    anilist: AccountOut | None = None  # linked AniList account
    # Entries being added to the other list after a sync, while that runs.
    writing: dict[str, ListWriteOut] | None = None
    # The list is being synced in the background (e.g. right after the first sign-in).
    syncing: bool = False
    # Shows friends recommended that the user hasn't looked at yet.
    recommendations_unseen: int = 0


class SyncResult(BaseModel):
    entries: int
    recommendations: int
    # With both lists linked: entries only one list had, being added to the other now.
    adding_to_mal: int = 0
    adding_to_anilist: int = 0
    skipped: int = 0  # AniList entries without a MyAnimeList id


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


class ScanProgressOut(BaseModel):
    """Running scans of a show: episodes stored so far out of those asked for."""

    stored: int
    total: int


class StreamFailureOut(ORM):
    episode: int
    option: str = Field(validation_alias="option_id")
    stream: str
    count: int
    failed_at: datetime


class StreamFailureIn(BaseModel):
    option: str = Field(max_length=200)
    stream: str = Field(max_length=100)


class ShowStreamsOut(BaseModel):
    """Everything the player needs for a show, to keep in the browser until `expires_at`."""

    providers: list[ProviderCoverageOut]
    scanning: bool
    expires_at: datetime
    cursor: int = 0  # server time (ms): pass as `after` for what changed since
    partial: bool = False  # only the episodes that changed (see `after`)
    progress: ScanProgressOut | None = None
    # Streams that wouldn't play recently: tried after the others (always the whole list).
    failures: list[StreamFailureOut] = []
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
    progress: ScanProgressOut | None = None


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


class ScoreUpdate(BaseModel):
    score: int = Field(ge=0, le=10)  # 0 removes the score


class ListStatusUpdate(BaseModel):
    status: Literal["watching", "completed", "on_hold", "dropped", "plan_to_watch"]


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


class StatsStatusOut(BaseModel):
    """The statistics page: cached statistics, and whether newer ones are being computed."""

    status: Literal["ready", "loading", "failed"]
    step: Literal["starting", "details", "computing"] | None = None  # what's being done
    done: int = 0
    total: int = 0
    error: str | None = None
    stats: StatsOut | None = None  # while loading: the previous statistics, if any
    computed_at: datetime | None = None


class CalendarOut(BaseModel):
    """Episodes airing between two times (Japanese broadcast, from AniList), in order."""

    items: list[AnimeCard]  # one per episode, with `airing` set
    refreshing: bool  # the schedule is being updated; ask again shortly


class PreviewOut(BaseModel):
    """A muted preview for a show's hover card: a direct stream of an episode, started at its
    opening when that's known."""

    episode: int
    language: str
    url: str
    format: Literal["hls", "file"] | None
    start_s: float


# Watch Together


class PairSide(BaseModel):
    """One user's side of a show: their list status and score, else their predicted score."""

    status: str | None = None
    score: int | None = None
    predicted: float | None = None
    appeal: float = 0.0  # how much they'd like it, in standard deviations of their scores


class PairOut(BaseModel):
    me: PairSide | None  # None: a guest, or someone without a list
    partner: PairSide | None


class PersonOut(BaseModel):
    id: int
    name: str
    picture: str | None = None


class InviteOut(BaseModel):
    code: str
    expires_at: datetime


class GuestIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class InviteInfo(BaseModel):
    inviter: PersonOut
    expires_at: datetime
    own: bool = False  # the viewer made it
    connection_id: int | None = None  # already connected with the inviter


class RoomStream(BaseModel):
    language: str | None = None
    provider: str | None = None
    label: str | None = None  # the source
    server: str | None = None  # the stream within it


class RoomState(BaseModel):
    rev: int
    anime_id: int
    episode: int
    title: str | None = None
    position: float
    playing: bool
    at: int  # server time of `position`, ms since the epoch
    by: int
    action: str
    stream: RoomStream | None = None


class Presence(BaseModel):
    user_id: int
    anime_id: int | None = None
    episode: int | None = None


class RoomOut(BaseModel):
    state: RoomState | None
    members: list[Presence]
    now: int  # server time, ms


class RoomUpdate(BaseModel):
    action: Literal["load", "play", "pause", "seek", "stream"]
    anime_id: int
    episode: int = Field(ge=1)
    position: float = Field(ge=0)
    playing: bool | None = None
    stream: RoomStream | None = None


class ConnectionOut(BaseModel):
    id: int
    partner: PersonOut
    created_at: datetime
    compatibility: int | None = None
    # The partner has a watch page open in the room (and the viewer doesn't): join them.
    partner_watching: RoomState | None = None
    partner_online: bool = False


class CompatibilityOut(BaseModel):
    score: int | None  # 0-100
    correlation: float | None  # of the scores both gave
    genre_similarity: float | None
    shared: int  # shows both have seen
    both_scored: int
    shared_genres: list[str]
    disagreements: list[AnimeCard]


class TogetherOut(BaseModel):
    id: int
    me: PersonOut
    partner: PersonOut
    compatibility: CompatibilityOut
    rows: list[Row]
    computed_at: datetime
    # Whose lists the recommendations use (a guest, or someone without a list, has none).
    me_list: bool = True
    partner_list: bool = True


# AnimeCard.pair refers to PairOut, defined after it.
AnimeCard.model_rebuild()
AnimeDetail.model_rebuild()


# The shared stream library (see services/library.py)
LIBRARY_SOURCE = r"^[a-z0-9_-]{1,30}/[A-Za-z0-9_]{1,48}$"


class SharedOptionIn(BaseModel):
    id: str = Field(max_length=500)
    label: str = Field(max_length=200)
    language: Literal["de-dub", "de-sub", "en-dub", "en-sub", "unknown"]
    resolved: dict | None = None


class SharedEpisodeIn(BaseModel):
    episode: int = Field(ge=0, le=10_000)
    options: list[SharedOptionIn] = Field(max_length=100)


class SharedSourcesIn(BaseModel):
    anime_id: int = Field(gt=0)
    source: str = Field(pattern=LIBRARY_SOURCE)
    episodes: list[SharedEpisodeIn] = Field(max_length=3000)


class SharedEpisodeOut(BaseModel):
    episode: int
    options: list[dict]
    updated_at: datetime


class SharedSourceOut(BaseModel):
    source: str
    episodes: list[SharedEpisodeOut]


# Recommending shows to friends (see api/friends.py)


class FriendRecommendationIn(BaseModel):
    anime_id: int = Field(gt=0)
    # The friends' connections (see /together) it goes to.
    connection_ids: list[int] = Field(min_length=1, max_length=50)
    message: str | None = Field(None, max_length=300)


class FriendRecommendationOut(BaseModel):
    id: int
    # Who recommended it (received) or who it went to (sent).
    person: PersonOut
    anime: AnimeCard
    message: str | None
    created_at: datetime
    seen: bool
    dismissed: bool = False
    # Sent: where the friend is with it on their list (None: not on it).
    their_progress: Progress | None = None


class FriendRecommendationsOut(BaseModel):
    received: list[FriendRecommendationOut]
    sent: list[FriendRecommendationOut]
    unseen: int


class FriendForShowOut(BaseModel):
    """A friend, as the recommend dialog of a show lists them."""

    connection_id: int
    person: PersonOut
    # Already recommended to them (when), and where they are with the show on their list.
    recommended_at: datetime | None = None
    their_progress: Progress | None = None


class ShowRecommendationsOut(BaseModel):
    friends: list[FriendForShowOut]
    # Friends who recommended this show to the viewer.
    received: list[FriendRecommendationOut]


class SharedSynopsisIn(BaseModel):
    anime_id: int = Field(gt=0)
    language: str = Field(pattern=r"^[a-z]{2}$")
    synopsis: str = Field(min_length=1, max_length=20_000)
    source: str | None = Field(None, max_length=20)


class PrefetchShowIn(BaseModel):
    id: int = Field(gt=0)
    episode: int = Field(1, ge=1, le=10_000)  # the user's next episode


class PrefetchIn(BaseModel):
    shows: list[PrefetchShowIn] = Field(max_length=300)


class PrefetchOut(BaseModel):
    queued: int


class SessionOut(BaseModel):
    """A Watch Together session: who joined it; active once both have."""

    connection_id: int
    partner: PersonOut
    joined: list[int]
    active: bool


class FriendCodeOut(BaseModel):
    code: str  # "ABCD-EFGH"


class FriendCodeIn(BaseModel):
    code: str = Field(min_length=4, max_length=20)


class PlaylistItemOut(BaseModel):
    anime: AnimeCard
    # The episode it plays; None: no aired episode left to watch (waiting for the next one).
    episode: int | None
    auto: bool  # taken in as an airing show with new episodes


class PlaylistOut(BaseModel):
    auto_airing: bool
    items: list[PlaylistItemOut]


class PlaylistAdd(BaseModel):
    anime_id: int


class PlaylistOrder(BaseModel):
    anime_ids: list[int] = Field(max_length=1000)


class PlaylistSettings(BaseModel):
    auto_airing: bool
