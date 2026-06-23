import {
	PosterResponse,
	SearchResponse,
	MovieDetail,
	TvDetail,
	EpisodeDetail,
	InteractTorrentResponse,
	TorrentProgress,
	SubtitleTrack,
	WipeResponse,
	Torrent,
} from "./types.js";

export async function fetchPosters(): Promise<PosterResponse> {
	const res = await fetch("/api/posters");
	if (!res.ok) throw new Error(`Request failed: ${res.status}`);
	return res.json();
}

export async function fetchSearchResults(query: string): Promise<SearchResponse> {
	const res = await fetch(`/api/search/${encodeURIComponent(query)}`);
	if (!res.ok) throw new Error(`Request failed: ${res.status}`);
	return res.json();
}

/** Thrown when a fetch returns 404, so callers can distinguish "not found"
 * from other failures without inspecting status codes themselves. */
export class NotFoundError extends Error {}

export async function fetchMovieDetail(movieId: string): Promise<MovieDetail> {
	const res = await fetch(`/api/movie/${encodeURIComponent(movieId)}`);
	if (!res.ok) {
		if (res.status === 404) throw new NotFoundError("Movie not found.");
		throw new Error(`Request failed: ${res.status}`);
	}
	return res.json();
}

export async function fetchTvDetail(tvId: string): Promise<TvDetail> {
	const res = await fetch(`/api/tv/${encodeURIComponent(tvId)}`);
	if (!res.ok) {
		if (res.status === 404) throw new NotFoundError("TV show not found.");
		throw new Error(`Request failed: ${res.status}`);
	}
	return res.json();
}

export async function fetchEpisodeDetail(
	tvId: string,
	season: number,
	episode: number
): Promise<EpisodeDetail> {
	const res = await fetch(
		`/api/tv/${encodeURIComponent(tvId)}/${encodeURIComponent(season)}/${encodeURIComponent(episode)}`
	);
	if (!res.ok) {
		if (res.status === 404) throw new NotFoundError("Episode not found.");
		throw new Error(`Request failed: ${res.status}`);
	}
	return res.json();
}


export async function postInteractTorrent(torrent: Torrent): Promise<{ success: boolean; hash: string }> {
	const res = await fetch("/interactTorrent", {
		method: "POST",
		headers: { "Content-Type": "application/json" },
		body: JSON.stringify({ link: torrent.magnet }),
	});
	if (!res.ok) throw new Error(`postInteractTorrent failed: ${res.status}`);
	return res.json();
}
 
export async function fetchTorrentProgress(hash: string): Promise<TorrentProgress> {
	const res = await fetch(`/torrentProgress?hash=${encodeURIComponent(hash)}`);
	if (!res.ok) throw new Error(`fetchTorrentProgress failed: ${res.status}`);
	return res.json();
}
 
export async function fetchStreamPrepare(hash: string): Promise<{ status: string; playlist: string }> {
	const res = await fetch(`/stream/${encodeURIComponent(hash)}/prepare`);
	if (!res.ok) throw new Error(`fetchStreamPrepare failed: ${res.status}`);
	return res.json();
}
 
export async function fetchSubtitleTracks(hash: string): Promise<SubtitleTrack[]> {
	const res = await fetch(`/subtitles/${encodeURIComponent(hash)}`);
	if (!res.ok) throw new Error(`fetchSubtitleTracks failed: ${res.status}`);
	return res.json();
}

export async function fetchCancelTorrent(hash: string): Promise<{ success: boolean }> {
	const res = await fetch(`/cancelTorrent?hash=${encodeURIComponent(hash)}`, {
		method: "POST",
	});
	if (!res.ok) throw new Error(`fetchCancelTorrent failed: ${res.status}`);
	return res.json();
}


export async function postWipeAll(deleteFiles: boolean): Promise<WipeResponse> {
	const res = await fetch(`/admin/wipe-all?delete_files=${deleteFiles}`, {
		method: "DELETE",
	});
	if (!res.ok) {
		const errBody = await res.json().catch(() => ({}));
		throw new Error(errBody.detail || `Request failed: ${res.status}`);
	}
	return res.json();
}

export async function postWipeHls(): Promise<WipeResponse> {
    const res = await fetch("/admin/wipe-hls", {
        method: "DELETE",
    });
    if (!res.ok) {
        const errBody = await res.json().catch(() => ({}));
        throw new Error(errBody.detail || `Request failed: ${res.status}`);
    }
    return res.json();
}

/** Extracts an ID/slug from a path like /movie/123 or /tv/456 or /search/inception
 * (the second path segment). Shared by movie, tv, and search pages. */
export function getIdFromPath(): string {
	const parts = window.location.pathname.split("/");
	return decodeURIComponent(parts[2] ?? "");
}
