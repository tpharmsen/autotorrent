/** Strips the file extension, mirroring Python's poster.rsplit('.', 1)[0] */
function stripExtension(filename) {
    const lastDot = filename.lastIndexOf(".");
    return lastDot === -1 ? filename : filename.slice(0, lastDot);
}
function renderCard(poster) {
    const slug = stripExtension(poster);
    return `
    <a href="/movie/${encodeURIComponent(slug)}">
      <div class="card">
        <img src="/posters/${encodeURIComponent(poster)}" alt="${escapeHtml(poster)}">
      </div>
    </a>
  `;
}
function escapeHtml(value) {
    return value
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}
export function renderPage(data) {
    const cards = data.posters.map(renderCard).join("\n");
    return `<!DOCTYPE html>
<html>
<head>
<title>Movie Posters</title>
<link rel="stylesheet" href="/static/styles.css">
</head>
<body>
<h1>🎬 Movie Posters</h1>
<div class="search-container">
  <input type="text" id="movie-search" placeholder="Search for a movie...">
  <button id="search-btn">Search</button>
</div>
<div class="grid">
${cards}
</div>
<div class="wipe-container">
  <button id="wipe-btn">Wipe Cache</button>
</div>
<script type="module" src="/static/client.js"></script>
</body>
</html>`;
}
//# sourceMappingURL=render.js.map