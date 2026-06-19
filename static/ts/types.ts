// types.ts
export interface Poster {
  filename: string;
}

export interface PageData {
  posters: string[]; // e.g. ["inception.jpg", "dune.png"]
}

export interface WipeResponse {
  torrents_removed: number;
}