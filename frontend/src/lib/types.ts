export type Progress = {
  status: "watching" | "completed" | "on_hold" | "dropped" | "plan_to_watch";
  episodes_watched: number;
  score: number;
  /** Linked lists the change couldn't be saved to (progress updates only). */
  failed?: ListProvider[];
};

export type Tier = "must_watch" | "recommended" | "maybe" | "skip" | "avoid";

/** The viewer's predicted score for a show they haven't scored (from their MAL list). */
export type Prediction = {
  score: number;
  tier: Tier;
  /** The features that moved the prediction most (detail page only). */
  reasons: { key: string; name: string; points: number }[];
};

export type TagCategory = "genre" | "theme" | "demographic" | "explicit";

export type AnimeCard = {
  id: number;
  title: string;
  title_en: string | null;
  picture_url: string | null;
  media_type: string | null;
  num_episodes: number | null;
  mean: number | null;
  genres: string[];
  progress: Progress | null;
  reason: string | null;
  prediction: Prediction | null;
  /** In the release calendar / New Episodes: this episode and its (Japanese) air time. */
  airing?: { episode: number; airing_at: string } | null;
  /** Signed in: where the user stopped in the episode they're watching. */
  resume?: { episode: number; position_s: number; duration_s: number | null } | null;
  status: string | null;
  start_season: string | null;
  /** While airing: the next episode and its air time. */
  next_episode: number | null;
  next_episode_at: string | null;
  /** Watch Together: both users' side of the show. */
  pair?: { me: PairSide | null; partner: PairSide | null } | null;
};

/** One user's side of a show: their list status and score, else their predicted score. */
export type PairSide = {
  status: string | null;
  score: number | null;
  predicted: number | null;
  appeal: number;
};

/** GET /anime/{id}/preview: a muted preview for the hover card. */
export type Preview = {
  episode: number;
  language: Language;
  url: string;
  format: "hls" | "file" | null;
  start_s: number;
};

export type AnimeDetail = AnimeCard & {
  synopsis: string | null;
  /** "en" is MAL's; another language when a translation was found. */
  synopsis_language: string;
  /** Episodes aired so far (null: no limit known, e.g. finished) and the next one's air time. */
  aired_episodes: number | null;
  status: string | null;
  start_season: string | null;
  tags: { id: number; name: string; category: TagCategory }[];
  studios: string[];
  source: string | null;
  rank: number | null;
  num_list_users: number | null;
};

export type SearchResponse = {
  items: AnimeCard[];
  page: number;
  has_next: boolean;
  source: "mal" | "jikan" | "local";
};

export type Genre = { id: number; name: string; category: TagCategory; count: number | null };

export type ShowRef = {
  id: number;
  title: string;
  title_en: string | null;
  picture_url: string | null;
  mean: number | null;
  score: number | null;
  prediction: Prediction | null;
};

export type TagStat = {
  key: string;
  name: string;
  kind: string;
  count: number;
  share: number;
  scored: number;
  mean_score: number | null;
  mal_mean: number | null;
  delta: number | null;
  affinity: number | null;
  weight: number | null;
  dropped: number;
};

export type HotTake = {
  kind: string;
  params: Record<string, number | string | null>;
  value: number | null;
  anime: ShowRef | null;
};

export type Stats = {
  overview: {
    total: number;
    by_status: { status: Progress["status"]; count: number }[];
    episodes: number;
    days: number | null;
    scored: number;
    mean_score: number | null;
    median_score: number | null;
    std_score: number | null;
    mal_mean: number | null;
    mean_difference: number | null;
    mean_abs_difference: number | null;
    agreement: number | null;
    median_members: number | null;
    drop_rate: number | null;
  };
  score_distribution: { score: number; mine: number; mal: number }[];
  favourites: TagStat[];
  hated: TagStat[];
  breakdown: Record<string, TagStat[]>;
  hot_takes: HotTake[];
  model: {
    scored: number;
    mae: number | null;
    baseline_mae: number | null;
    mal_weight: number | null;
    thresholds: number[];
    likes: { key: string; name: string; kind: string; points: number }[];
    dislikes: { key: string; name: string; kind: string; points: number }[];
  } | null;
  plan_to_watch: ShowRef[];
};

export type Row = { id: string; title: string; items: AnimeCard[] };

export type BrowseResponse = {
  hero: AnimeDetail | null;
  rows: Row[];
  signed_in: boolean;
  mal_configured: boolean;
  anilist_configured: boolean;
};

export type ListProvider = "mal" | "anilist";

export type Me = {
  id: number;
  name: string;
  picture: string | null;
  last_synced_at: string | null;
  /** Watch Together without a list (joined through an invite link with a name). */
  guest: boolean;
  /** Linked lists. */
  mal: { name: string | null } | null;
  anilist: { name: string | null } | null;
  /** Entries being added to the other list after a sync. */
  writing: Record<ListProvider, { done: number; total: number; failed: number }> | null;
};

export type SkipSegment = {
  kind: "opening" | "ending";
  start_s: number;
  end_s: number;
  confidence: number;
  source: "analysis" | "manual" | "provider" | "aniskip";
};

export type Episode = {
  anime_id: number;
  episode: number;
  skip_segments: SkipSegment[];
};

export type Language = "de-dub" | "de-sub" | "en-dub" | "en-sub" | "unknown";

export type Subtitle = { url: string; label: string; lang: string | null };

export type Stream = {
  kind: "embed" | "direct";
  url: string;
  label: string;
  format: "hls" | "file" | null;
  subtitles: Subtitle[];
};

export type Resolved = {
  streams: Stream[];
  skip_segments: SkipSegment[];
  /** When these links were fetched, and until when they may be reused (from the API). */
  resolved_at?: string | null;
  expires_at?: string | null;
};

export type SourceOption = {
  id: string;
  provider: string;
  label: string;
  language: Language;
  resolved: Resolved | null;
};

export type ProviderMapping = {
  provider: string;
  external_id: string | null;
  season: number | null;
  episode_offset: number;
  manual: boolean;
};

export type AnalysisJob = {
  id: string;
  anime_id: number;
  episodes: number[];
  language: Language | null;
  compare: boolean;
  redownload: boolean;
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type EpisodeAnalysis = { episode: number; analysed: boolean; segments: SkipSegment[] };

export type ReferenceFingerprint = {
  id: number;
  kind: "opening" | "ending";
  source_episode: number;
  duration_s: number;
};

export type AnalysisOverview = {
  episodes: EpisodeAnalysis[];
  references: ReferenceFingerprint[];
  running: AnalysisJob[];
};

export type ProviderScan = {
  provider: string;
  status: "running" | "done" | "failed";
  error: string | null;
  finished_at: string | null;
};

export type Availability = {
  episodes: { episode: number; languages: Language[] }[];
  checked: number[];
  scans: ProviderScan[];
  scanning: boolean;
};

/** GET /me/stats: statistics are computed in the background; poll while "loading". */
export type StatsStatus = {
  status: "ready" | "loading" | "failed";
  step: "starting" | "details" | "computing" | null;
  done: number;
  total: number;
  error: string | null;
  /** While loading: the previous statistics, if there are any. */
  stats: Stats | null;
  computed_at: string | null;
};

export type CalendarResponse = { items: AnimeCard[]; refreshing: boolean };

// Watch Together

export type Person = { id: number; name: string; picture: string | null };

export type RoomStream = {
  language: string | null;
  provider: string | null;
  label: string | null;
  server: string | null;
};

/** What a Watch Together room is playing: `position` at server time `at` (ms). */
export type RoomState = {
  rev: number;
  anime_id: number;
  episode: number;
  title: string | null;
  position: number;
  playing: boolean;
  at: number;
  by: number;
  action: "load" | "play" | "pause" | "seek" | "stream";
  stream: RoomStream | null;
};

export type Presence = { user_id: number; anime_id: number | null; episode: number | null };

export type RoomOut = { state: RoomState | null; members: Presence[]; now: number };

export type Connection = {
  id: number;
  partner: Person;
  created_at: string;
  compatibility: number | null;
  /** The partner is watching in the room (and you aren't): join them. */
  partner_watching: RoomState | null;
  partner_online: boolean;
};

export type InviteInfo = {
  inviter: Person;
  expires_at: string;
  own: boolean;
  connection_id: number | null;
};

export type Together = {
  id: number;
  me: Person;
  partner: Person;
  compatibility: {
    score: number | null;
    correlation: number | null;
    genre_similarity: number | null;
    shared: number;
    both_scored: number;
    shared_genres: string[];
    disagreements: AnimeCard[];
  };
  rows: Row[];
  computed_at: string;
  /** Whose lists the recommendations use (a guest, or an empty list, has none). */
  me_list: boolean;
  partner_list: boolean;
};
