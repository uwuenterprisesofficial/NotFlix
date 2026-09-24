export type Progress = {
  status: "watching" | "completed" | "on_hold" | "dropped" | "plan_to_watch";
  episodes_watched: number;
  score: number;
};

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
};

export type AnimeDetail = AnimeCard & {
  synopsis: string | null;
  status: string | null;
  start_season: string | null;
};

export type Row = { id: string; title: string; items: AnimeCard[] };

export type BrowseResponse = {
  hero: AnimeDetail | null;
  rows: Row[];
  signed_in: boolean;
  mal_configured: boolean;
};

export type Me = {
  id: number;
  name: string;
  picture: string | null;
  last_synced_at: string | null;
};

export type SkipSegment = {
  kind: "opening" | "ending";
  start_s: number;
  end_s: number;
  confidence: number;
  source: "analysis" | "manual" | "provider";
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

export type Resolved = { streams: Stream[]; skip_segments: SkipSegment[] };

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
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
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
