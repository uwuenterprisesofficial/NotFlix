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

export type Source = { provider: string; kind: "embed" | "direct"; url: string };

export type SkipSegment = {
  kind: "opening" | "ending";
  start_s: number;
  end_s: number;
  confidence: number;
  source: string;
};

export type Episode = {
  anime_id: number;
  episode: number;
  sources: Source[];
  skip_segments: SkipSegment[];
};

export type AnalysisJob = {
  id: string;
  anime_id: number;
  episodes: number[];
  status: "queued" | "running" | "done" | "failed";
  error: string | null;
};
