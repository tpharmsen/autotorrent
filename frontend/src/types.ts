export interface Poster {
  filename: string;
}

export type PosterResponse = {
  movies: string[];
  tv: string[];
}

export interface WipeResponse {
  status: boolean | string;
  torrents_removed: number;
  files_deleted: boolean;
  detail?: string;
}

// ── Search ──────────────────────────────────────────────
export interface SearchResultMovie {
  id: number;
  title?: string;
  name?: string; // TMDB sometimes returns `name` instead of `title` (TV results)
  poster_path?: string | null;
  release_date?: string;
}

export interface SearchResponse {
  movies: SearchResultMovie[];
  tv: SearchResultMovie[];
}

// ── Movie detail ────────────────────────────────────────
export interface CastMember {
  name: string;
  character: string;
}

export interface Credits {
  cast: CastMember[];
}

export interface VideoResult {
  type: string;
  site: string;
  key: string;
}

export interface Videos {
  results: VideoResult[];
}

export interface Torrent {
  name: string;
  quality?: string;
  size?: string;
  seeders: number;
  leechers: number;
  magnet: string;
}

export interface MovieDetail {
  id: number;
  title: string;
  overview?: string;
  release_date?: string;
  poster_path?: string | null;
  vote_average?: number;
  runtime?: number;
  credits?: Credits;
  videos?: Videos;
  torrents: Torrent[];
}

export interface InteractTorrentResponse {
  success: boolean;
  hash: string;
}

export interface TorrentProgress {
  name: string;
  completed_mb: number;
  status: string;
}

export interface SubtitleTrack {
  index: number;
  title: string;
  language: string;
}