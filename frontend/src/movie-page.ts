import { MovieDetail } from "./types.js";
import { renderMovieDetail, renderTorrentList } from "./render.js";
import { getIdFromPath, fetchMovieDetail, NotFoundError } from "./api.js";
import { interactTorrent, clearProgressInterval } from "./player.js";

async function loadMovie(): Promise<void> {
	const movieId = getIdFromPath();
	if (!movieId) return;

	try {
		const movie: MovieDetail = await fetchMovieDetail(movieId);
		document.title = movie.title;
		renderMovieDetail(movie);
		renderTorrentList(movie.torrents, interactTorrent);
	} catch (err) {
		const detailEl = document.getElementById("movie-detail");
		if (err instanceof NotFoundError) {
			if (detailEl) detailEl.innerHTML = `<p>Movie not found.</p>`;
			return;
		}
		console.error("Failed to load movie:", err);
		if (detailEl) detailEl.innerHTML = `<p>Failed to load movie details.</p>`;
	}
}

document.addEventListener("DOMContentLoaded", () => {
	loadMovie();
});

window.addEventListener("beforeunload", () => {
	clearProgressInterval();
});
