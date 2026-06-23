import { renderPosterGrid } from "./render.js";
import { fetchPosters, postWipeHls, postWipeAll } from "./api.js";

async function loadPosters(): Promise<void> {
	try {
		const data = await fetchPosters();
		renderPosterGrid(data.movies, "movie", "movie-grid");
		renderPosterGrid(data.tv, "tv", "tv-grid");
	} catch (err) {
		console.error("Failed to load posters:", err);
		showGridError("movie-grid");
		showGridError("tv-grid");
	}
}

function showGridError(containerId: string): void {
	const container = document.getElementById(containerId);
	if (!container) return;
	container.innerHTML = `<p class="error">Failed to load posters.</p>`;
}

function initSearch(): void {
	const input = document.getElementById("movie-search") as HTMLInputElement | null;
	const button = document.getElementById("search-btn");
	if (!input || !button) return;

	const goSearch = (): void => {
		const query = input.value.trim();
		if (!query) return;
		window.location.href = `/search/${encodeURIComponent(query)}`;
	};

	button.addEventListener("click", goSearch);
	input.addEventListener("keydown", (e: KeyboardEvent) => {
		if (e.key === "Enter") goSearch();
	});
}

function hlsWipe(): void {
	const button = document.getElementById("hls-wipe-btn");
	if (!button) return;

	button.addEventListener("click", async () => {
		const confirmed = window.confirm(
			"This will delete all HLS files. Continue?"
		);
		if (!confirmed) return;

		try {
			const data = await postWipeHls();
			if (data.status === "error") {
				window.alert(`Wipe failed: ${data.detail ?? "unknown error"}`);
				return;
			}
			window.alert(`Wipe complete\nHLS files removed: ${data.files_removed}`);
			window.location.reload();
		} catch (err) {
			console.error("Wipe failed:", err);
			window.alert("Wipe failed — check console for details.");
		}
	});
}

function totalWipe(): void {
	const button = document.getElementById("total-wipe-btn");
	if (!button) return;

	button.addEventListener("click", async () => {
		const confirmed = window.confirm(
			"This will delete all torrents + files + streams. Continue?"
		);
		if (!confirmed) return;

		try {
			const data = await postWipeAll(true);
			if (data.status === "error") {
				window.alert(`Wipe failed: ${data.detail ?? "unknown error"}`);
				return;
			}
			window.alert(`Wipe complete\nFiles removed: ${data.files_removed}`);
			window.location.reload();
		} catch (err) {
			console.error("Wipe failed:", err);
			window.alert("Wipe failed — check console for details.");
		}
	});
}

document.addEventListener("DOMContentLoaded", () => {
	initSearch();
	hlsWipe();
    totalWipe();
	loadPosters();
});
