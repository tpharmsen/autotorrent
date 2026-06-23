import { TvDetail, EpisodeDetail } from "./types.js";
import { escapeHtml, renderTorrentList } from "./render.js";
import { getIdFromPath, fetchTvDetail, fetchEpisodeDetail, NotFoundError } from "./api.js";
import { interactTorrent } from "./player.js";

function renderTvDetail(tv: TvDetail): void {
	const container = document.getElementById("tv-detail");
	if (!container) return;

	const posterUrl = tv.poster_path
		? `https://image.tmdb.org/t/p/w500${tv.poster_path}`
		: "/static/placeholder.png";

	const beginyear = tv.first_air_date ? tv.first_air_date.slice(0, 4) : "";
	const endyear = tv.last_air_date ? tv.last_air_date.slice(0, 4) : "";
	const rating = tv.vote_average !== undefined ? tv.vote_average.toFixed(1) : "?";
	const runtime = tv.runtime !== undefined ? `${tv.runtime} min` : "";
	const seasons = tv.number_of_seasons !== undefined ? `${tv.number_of_seasons} season${tv.number_of_seasons !== 1 ? "s" : ""}` : "";
	const episodes = tv.number_of_episodes !== undefined ? `${tv.number_of_episodes} episode${tv.number_of_episodes !== 1 ? "s" : ""}` : "";

	const castHtml = (tv.credits?.cast ?? [])
		.slice(0, 10)
		.map(
			(member) =>
				`<div class="actor">${escapeHtml(member.name)} <span class="character">as ${escapeHtml(member.character)}</span></div>`
		)
		.join("\n");

	container.innerHTML = `
    <div class="hero">
      <div class="poster">
        <img src="${posterUrl}" alt="${escapeHtml(tv.name)}">
      </div>
      <div class="info">
        <h1>${escapeHtml(tv.name)}</h1>
        <div class="meta">${escapeHtml(beginyear)} - ${escapeHtml(endyear)} · ⭐ ${rating} · ${escapeHtml(runtime)} · ${escapeHtml(seasons)} · ${escapeHtml(episodes)}</div>
        <div class="overview">${tv.overview ? escapeHtml(tv.overview) : ""}</div>
        <h2>Cast</h2>
        <div class="cast">${castHtml}</div>
      </div>
    </div>
  `;
}

const seasonSelect = document.getElementById(
	"season-select"
) as HTMLSelectElement;

const episodeSelect = document.getElementById(
	"episode-select"
) as HTMLSelectElement;

let currentEpisodeStructure: Record<number, number> = {};

function populateSeasons(episode_structure: Record<number, number>) {
	seasonSelect.innerHTML = "";

	Object.keys(episode_structure)
		.map(Number)
		.sort((a, b) => a - b)
		.forEach((season) => {
			const option = document.createElement("option");
			option.value = season.toString();
			option.textContent = `Season ${season}`;
			seasonSelect.appendChild(option);
		});
}

function populateEpisodes(episode_structure: Record<number, number>, season: number) {
	episodeSelect.innerHTML = "";

	const episodeCount = episode_structure[season];
	for (let i = 1; i <= episodeCount; i++) {
		const option = document.createElement("option");
		option.value = i.toString();
		option.textContent = `Episode ${i}`;
		episodeSelect.appendChild(option);
	}
}

/** Clears episode detail + torrent list. Used whenever the current
 * dropdown state no longer corresponds to a user-confirmed selection. */
function clearEpisodeAndTorrents(): void {
	const episodeDetailEl = document.getElementById("episode-detail");
	if (episodeDetailEl) episodeDetailEl.innerHTML = "";

	const torrentListEl = document.getElementById("torrent-list");
	if (torrentListEl) torrentListEl.innerHTML = "";
}

function renderSeasonSelect(episode_structure: Record<number, number>) {
	currentEpisodeStructure = episode_structure;

	populateSeasons(episode_structure);

	const firstSeason = Number(Object.keys(episode_structure)[0]);

	seasonSelect.value = firstSeason.toString();

	populateEpisodes(episode_structure, firstSeason);

	clearEpisodeAndTorrents();
}

async function loadTv(): Promise<void> {
	const tvId = getIdFromPath();
	if (!tvId) return;

	try {
		const tv: TvDetail = await fetchTvDetail(tvId);
		const episodeStructure = tv.episode_structure || {};
		document.title = tv.name;
		renderTvDetail(tv);
		renderSeasonSelect(episodeStructure);
	} catch (err) {
		const detailEl = document.getElementById("tv-detail");
		if (err instanceof NotFoundError) {
			if (detailEl) detailEl.innerHTML = `<p>TV show not found.</p>`;
			return;
		}
		console.error("Failed to load TV show:", err);
		if (detailEl) detailEl.innerHTML = `<p>Failed to load TV show details.</p>`;
	}
}

function renderEpisodeDetail(episode: EpisodeDetail): void {
	try {
		const container = document.getElementById("episode-detail");
		if (container) {
			container.innerHTML = `
				<h3>${episode.name}</h3>
				<p>Air Date: ${episode.air_date || "N/A"}</p>
				<p>Rating: ${episode.vote_average !== undefined ? episode.vote_average.toFixed(1) : "N/A"} ⭐</p>
				<p>Overview: ${episode.overview || "N/A"}</p>
			`;
		}
	} catch (err) {
		console.error("Failed to render episode detail:", err);
	}
}

async function loadEpisode(season: number, episode: number): Promise<void> {
	const tvId = getIdFromPath();
	if (!tvId) return;

	try {
		const tv: EpisodeDetail = await fetchEpisodeDetail(tvId, season, episode);
		renderEpisodeDetail(tv);
		renderTorrentList(tv.torrents, interactTorrent);
	} catch (err) {
		const detailEl = document.getElementById("episode-detail");
		if (err instanceof NotFoundError) {
			if (detailEl) detailEl.innerHTML = `<p>Episode not found.</p>`;
			return;
		}
		console.error("Failed to load episode:", err);
		if (detailEl) detailEl.innerHTML = `<p>Failed to load episode details.</p>`;
	}
}

document.addEventListener("DOMContentLoaded", () => {
	loadTv();
});

seasonSelect.addEventListener("change", () => {
	const season = Number(seasonSelect.value);
	populateEpisodes(currentEpisodeStructure, season);
	clearEpisodeAndTorrents();
});

episodeSelect.addEventListener("change", () => {
	const season = Number(seasonSelect.value);
	const episode = Number(episodeSelect.value);

	loadEpisode(season, episode);
});
