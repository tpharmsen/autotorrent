import { SearchResultMovie, MovieDetail, Torrent } from "./types.js";

/** Strips the file extension, e.g. "inception.jpg" -> "inception" */
function stripExtension(filename: string): string {
  const lastDot = filename.lastIndexOf(".");
  return lastDot === -1 ? filename : filename.slice(0, lastDot);
}

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Renders the poster grid on the home page into #poster-grid */
export function renderPosterGrid(posters: string[]): void {
  const container = document.getElementById("poster-grid");
  if (!container) return;

  container.innerHTML = posters
    .map((poster) => {
      const slug = stripExtension(poster);
      return `
        <a href="/movie/${encodeURIComponent(slug)}">
          <div class="card">
            <img src="/posters/${encodeURIComponent(poster)}" alt="${escapeHtml(poster)}">
          </div>
        </a>
      `;
    })
    .join("\n");
}

/**
 * Renders search results as a vertical list into #search-results,
 * matching the old Jinja2 search.html (.list / .list-item layout).
 * Falls back to movie.name if movie.title is absent (TV-style results),
 * and shows a placeholder block when there's no poster.
 */
export function renderSearchResults(movies: SearchResultMovie[]): void {
  const container = document.getElementById("search-results");
  if (!container) return;

  if (movies.length === 0) {
    container.innerHTML = `<div class="empty">No results found.</div>`;
    return;
  }

  container.innerHTML = movies
    .map((movie) => {
      const displayTitle = movie.title || movie.name || "";
      const year = movie.release_date ? movie.release_date.slice(0, 4) : "";

      const posterHtml = movie.poster_path
        ? `<img src="https://image.tmdb.org/t/p/w185${movie.poster_path}" alt="">`
        : `<div class="placeholder"></div>`;

      return `
        <a class="list-item" href="/movie/${encodeURIComponent(displayTitle)}">
          ${posterHtml}
          <div class="info">
            <div class="title">${escapeHtml(displayTitle)}</div>
            <div class="year">${escapeHtml(year)}</div>
          </div>
          <span class="arrow">›</span>
        </a>
      `;
    })
    .join("\n");
}

/** Picks the first YouTube trailer from a movie's videos.results, if any */
function findTrailerKey(movie: MovieDetail): string | null {
  const trailer = movie.videos?.results.find(
    (v) => v.type === "Trailer" && v.site === "YouTube"
  );
  return trailer ? trailer.key : null;
}

/**
 * Renders the hero section (poster, title, meta, overview, cast) plus
 * trailer embed into #movie-detail. Mirrors the old Jinja2 movie.html.
 */
export function renderMovieDetail(movie: MovieDetail): void {
  const container = document.getElementById("movie-detail");
  if (!container) return;

  const posterUrl = movie.poster_path
    ? `https://image.tmdb.org/t/p/w500${movie.poster_path}`
    : "/static/placeholder.png";

  const year = movie.release_date ? movie.release_date.slice(0, 4) : "";
  const rating = movie.vote_average !== undefined ? movie.vote_average.toFixed(1) : "?";
  const runtime = movie.runtime !== undefined ? `${movie.runtime} min` : "";

  const castHtml = (movie.credits?.cast ?? [])
    .slice(0, 10)
    .map(
      (member) =>
        `<div class="actor">${escapeHtml(member.name)} <span class="character">as ${escapeHtml(member.character)}</span></div>`
    )
    .join("\n");

  const trailerKey = findTrailerKey(movie);
  const trailerHtml = trailerKey
    ? `
      <h2>Trailer</h2>
      <div class="trailer-wrap">
        <iframe src="https://www.youtube.com/embed/${encodeURIComponent(trailerKey)}" allowfullscreen></iframe>
      </div>
    `
    : "";

  container.innerHTML = `
    <div class="hero">
      <div class="poster">
        <img src="${posterUrl}" alt="${escapeHtml(movie.title)}">
      </div>
      <div class="info">
        <h1>${escapeHtml(movie.title)}</h1>
        <div class="meta">${escapeHtml(year)} · ⭐ ${rating} · ${escapeHtml(runtime)}</div>
        <div class="overview">${movie.overview ? escapeHtml(movie.overview) : ""}</div>
        <h2>Cast</h2>
        <div class="cast">${castHtml}</div>
      </div>
    </div>
    ${trailerHtml}
  `;
}

/**
 * Renders the torrent table into #torrent-list, matching the old
 * Name / Quality / Size / Seeds / Leeches / Stream-button layout.
 * onSelect fires when a row's Stream button is clicked.
 */
export function renderTorrentList(
  torrents: Torrent[],
  onSelect: (torrent: Torrent) => void
): void {
  const container = document.getElementById("torrent-list");
  if (!container) return;

  if (torrents.length === 0) {
    container.innerHTML = `<p>No torrents found.</p>`;
    return;
  }

  const rows = torrents
    .map(
      (t, i) => `
      <tr>
        <td class="torrent-name">${escapeHtml(t.name)}</td>
        <td>${t.quality ? escapeHtml(t.quality) : ""}</td>
        <td>${t.size ? escapeHtml(t.size) : ""}</td>
        <td class="seed">${t.seeders}</td>
        <td class="leech">${t.leechers}</td>
        <td><button class="magnet-btn" data-index="${i}">⬇ Stream</button></td>
      </tr>
    `
    )
    .join("\n");

  container.innerHTML = `
    <table class="torrent-table">
      <thead>
        <tr>
          <th>Name</th>
          <th>Quality</th>
          <th>Size</th>
          <th>Seeds</th>
          <th>Leeches</th>
          <th></th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
  `;

  container.querySelectorAll<HTMLButtonElement>(".magnet-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.dataset.index);
      onSelect(torrents[idx]);
    });
  });
}