import { SearchResponse } from "./types.js";
import { renderSearchResults } from "./render.js";

/** Extracts the query from a path like /search/inception */
function getQueryFromPath(): string {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[2] ?? "");
}

async function loadSearchResults(): Promise<void> {
  const query = getQueryFromPath();
  const container = document.getElementById("search-results");
  if (!query) {
    if (container) container.innerHTML = `<p>No search query provided.</p>`;
    return;
  }

  document.title = `Search: ${query}`;

  try {
    const res = await fetch(`/api/search/${encodeURIComponent(query)}`);
    if (!res.ok) throw new Error(`Request failed: ${res.status}`);
    const data: SearchResponse = await res.json();
    renderSearchResults(data.movies, 'movies', 'search-results-movie');
    renderSearchResults(data.tv, 'tv', 'search-results-tv');
  } catch (err) {
    console.error("Search failed:", err);
    
    showSearchError('search-results-movie');
    showSearchError('search-results-tv');
  }
}

function showSearchError(containerId: string): void {
  const container = document.getElementById(containerId);
  if (!container) return;

  container.innerHTML = `<p class="error">Failed to load search results.</p>`;
}

function initSearchBox(): void {
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

document.addEventListener("DOMContentLoaded", () => {
  initSearchBox();
  loadSearchResults();
});