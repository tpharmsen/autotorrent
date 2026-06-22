import {
  MovieDetail,
  Torrent,
  InteractTorrentResponse,
  TorrentProgress,
  SubtitleTrack,
} from "./types.js";
import { renderMovieDetail, renderTorrentList } from "./render.js";

// hls.js is loaded globally via <script src="https://cdn.jsdelivr.net/npm/hls.js@.../hls.min.js">
// in movie.html, not as an ES module — so we declare the global here.
declare const Hls: any;

const MIN_MB = 50;

function getIdFromPath(): string {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[2] ?? "");
}

let progressInterval: number | undefined;
let hlsInstance: any | null = null;

function getOverlay(): HTMLElement | null {
  return document.getElementById("overlay");
}

function showOverlay(): void {
  getOverlay()?.classList.add("active");
}

function hideOverlay(): void {
  getOverlay()?.classList.remove("active");
}

/** Stops and tears down any current playback, resetting the player UI. */
function stopPlayer(): void {
  const video = document.getElementById("video-player") as HTMLVideoElement | null;
  if (video) {
    video.pause();
    video.src = "";
    while (video.firstChild) video.removeChild(video.firstChild);
  }

  if (hlsInstance) {
    hlsInstance.destroy();
    hlsInstance = null;
  }

  document.getElementById("player-wrap")?.classList.remove("active");
  const subInfo = document.getElementById("subtitle-info");
  if (subInfo) subInfo.textContent = "";

  if (progressInterval) {
    window.clearInterval(progressInterval);
    progressInterval = undefined;
  }
}

/** Kicks off the HLS prepare step, attaches hls.js (or native HLS on Safari), loads subtitles. */
async function startPlayer(hash: string, name: string): Promise<void> {
  const video = document.getElementById("video-player") as HTMLVideoElement | null;
  const wrap = document.getElementById("player-wrap");
  if (!video || !wrap) return;

  stopPlayer();

  const titleEl = document.getElementById("player-title");
  if (titleEl) titleEl.textContent = name;

  wrap.classList.add("active");
  wrap.scrollIntoView({ behavior: "smooth" });

  const res = await fetch(`/stream/${hash}/prepare`);
  if (!res.ok) {
    window.alert("Failed to prepare HLS stream pipeline.");
    return;
  }

  const data: { playlist: string } = await res.json();
  const src = data.playlist; // e.g. "/stream/<hash>/hls/index.m3u8"

  while (video.firstChild) video.removeChild(video.firstChild);

  if (Hls.isSupported()) {
    hlsInstance = new Hls({
      lowLatencyMode: true,
      backBufferLength: 30,
    });
    hlsInstance.loadSource(src);
    hlsInstance.attachMedia(video);
    hlsInstance.on(Hls.Events.MANIFEST_PARSED, () => {
      video.play();
    });
  } else if (video.canPlayType("application/vnd.apple.mpegurl")) {
    // Native HLS support (Safari / iOS)
    video.src = src;
    video.play();
  } else {
    window.alert("HLS playback is not supported in this browser.");
  }

  try {
    const subRes = await fetch(`/subtitleTracks/${hash}`);
    const tracks: SubtitleTrack[] = await subRes.json();

    tracks.forEach((track, i) => {
      const el = document.createElement("track");
      el.kind = "subtitles";
      el.label = track.title;
      el.srclang = track.language;
      el.src = `/subtitles/${hash}/${track.index}`;
      if (i === 0) el.default = true;
      video.appendChild(el);
    });
  } catch (e) {
    console.warn("Subtitle initialization error:", e);
  }
}

/** Polls /torrentProgress until enough of the torrent has downloaded, then starts playback. */
function pollProgress(hash: string): void {
  showOverlay();

  progressInterval = window.setInterval(async () => {
    try {
      const res = await fetch(`/torrentProgress?hash=${encodeURIComponent(hash)}`);
      const { name, completed_mb, status }: TorrentProgress = await res.json();
      const pct = Math.min(100, Math.round((completed_mb / MIN_MB) * 100));

      setText("prog-name", name);
      setWidth("prog-fill", pct);
      setText("prog-bytes", `${completed_mb.toFixed(1)} MB of ${MIN_MB} MB`);
      setText("prog-pct", `${pct}%`);
      setText("prog-status", status || "Downloading — please wait…");

      if (completed_mb >= MIN_MB) {
        if (progressInterval) window.clearInterval(progressInterval);
        progressInterval = undefined;
        setText("prog-status", "Starting playback…");
        setTimeout(() => {
          hideOverlay();
          startPlayer(hash, name);
        }, 500);
      }
    } catch (err) {
      console.error("Progress check failed:", err);
    }
  }, 1000);
}

function setText(id: string, value: string): void {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function setWidth(id: string, pct: number): void {
  const el = document.getElementById(id) as HTMLElement | null;
  if (el) el.style.width = `${pct}%`;
}

/** Triggered when a torrent's Stream button is clicked. */
async function interactTorrent(torrent: Torrent): Promise<void> {
  stopPlayer();

  try {
    const res = await fetch("/interactTorrent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ link: torrent.magnet }),
    });
    if (!res.ok) {
      const errBody = await res.json().catch(() => ({}));
      throw new Error(errBody.detail || `Request failed: ${res.status}`);
    }
    const data: InteractTorrentResponse = await res.json();
    if (data.hash) pollProgress(data.hash);
  } catch (err) {
    console.error("Failed to start torrent:", err);
    window.alert("Failed to start torrent — check console for details.");
  }
}

async function loadMovie(): Promise<void> {
  const movieId = getIdFromPath();
  if (!movieId) return;

  try {
    const res = await fetch(`/api/movie/${encodeURIComponent(movieId)}`);
    if (!res.ok) {
      if (res.status === 404) {
        const detailEl = document.getElementById("movie-detail");
        if (detailEl) detailEl.innerHTML = `<p>Movie not found.</p>`;
        return;
      }
      throw new Error(`Request failed: ${res.status}`);
    }
    const movie: MovieDetail = await res.json();
    document.title = movie.title;
    renderMovieDetail(movie);
    renderTorrentList(movie.torrents, interactTorrent);
  } catch (err) {
    console.error("Failed to load movie:", err);
    const detailEl = document.getElementById("movie-detail");
    if (detailEl) detailEl.innerHTML = `<p>Failed to load movie details.</p>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  loadMovie();
});

window.addEventListener("beforeunload", () => {
  if (progressInterval) window.clearInterval(progressInterval);
});