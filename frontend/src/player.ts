import { Torrent } from "./types.js";
import { postInteractTorrent, fetchTorrentProgress, fetchSubtitleTracks, fetchStreamPrepare } from "./api.js";

// hls.js is loaded globally via <script src="https://cdn.jsdelivr.net/npm/hls.js@.../hls.min.js">
// in movie.html and tv.html, not as an ES module — so we declare the global here.
declare const Hls: any;

const MIN_MB = 20;

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

function setText(id: string, value: string): void {
	const el = document.getElementById(id);
	if (el) el.textContent = value;
}

function setWidth(id: string, pct: number): void {
	const el = document.getElementById(id) as HTMLElement | null;
	if (el) el.style.width = `${pct}%`;
}

/** Stops and tears down any current playback, resetting the player UI. */
export function stopPlayer(): void {
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

	let src: string;
	try {
		const data = await fetchStreamPrepare(hash);
		src = data.playlist; // e.g. "/stream/<hash>/hls/index.m3u8"
	} catch (err) {
		window.alert("Failed to prepare HLS stream pipeline.");
		return;
	}

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
		const tracks = await fetchSubtitleTracks(hash);
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
			const { name, safe_completed_mb, status } = await fetchTorrentProgress(hash);
			const pct = Math.min(100, Math.round((safe_completed_mb / MIN_MB) * 100));

			setText("prog-name", name);
			setWidth("prog-fill", pct);
			setText("prog-bytes", `${safe_completed_mb.toFixed(1)} MB of ${MIN_MB} MB`);
			setText("prog-pct", `${pct}%`);
			setText("prog-status", status || "Downloading — please wait…");

			if (safe_completed_mb >= MIN_MB) {
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

/** Triggered when a torrent's Stream button is clicked. */
export async function interactTorrent(torrent: Torrent): Promise<void> {
	stopPlayer();

	try {
		const data = await postInteractTorrent(torrent);
		if (data.hash) pollProgress(data.hash);
	} catch (err) {
		console.error("Failed to start torrent:", err);
		window.alert("Failed to start torrent — check console for details.");
	}
}

/** Clears the progress-polling interval. Call this from a page's
 * beforeunload handler to avoid leaking the timer. */
export function clearProgressInterval(): void {
	if (progressInterval) window.clearInterval(progressInterval);
}

