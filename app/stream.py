import os
import re
import json
import threading
import subprocess
import time
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from qb import (
    get_torrent_info,
    get_torrent_files,
    get_safe_contiguous_bytes,
)

VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".wmv")
from vars import HLS_BASE_DIR

os.makedirs(HLS_BASE_DIR, exist_ok=True)

# Minimum contiguous bytes required before we even attempt to start ffmpeg.
# This is deliberately generous (rather than "any bytes at all") because
# ffmpeg's own probing (-analyzeduration/-probesize) needs to see a real
# chunk of the file up front to detect codecs/container structure reliably.
MIN_INITIAL_SAFE_BYTES = 16 * 1024 * 1024  # 16 MB

# How often the feeder thread re-checks qBittorrent for newly-downloaded
# contiguous bytes once it has caught up to the current safe frontier.
POLL_INTERVAL_SECONDS = 1.0

# How long the feeder will wait for the download to advance past a stall
# point before giving up and closing the pipe (prevents an ffmpeg process
# + feeder thread from running forever against a dead/paused torrent).
STALL_TIMEOUT_SECONDS = 180

# Tracks active feeder threads so concurrent requests for the same hash
# don't spawn duplicate feeders/ffmpeg processes racing on the same output
# directory. Keyed by torrent_hash.
_active_feeders_lock = threading.Lock()
_active_feeders: dict[str, "_SafeFileFeeder"] = {}

# Tracks the live ffmpeg subprocess.Popen handle per torrent_hash, so a
# cancel request can actually terminate the running encode instead of just
# stopping the feeder thread (which alone would leave ffmpeg blocked
# forever on a now-abandoned FIFO read).
_active_processes_lock = threading.Lock()
_active_processes: dict[str, subprocess.Popen] = {}

# Hashes that have been cancelled mid-startup (i.e. while _ensure_hls was
# still waiting for an initial safe buffer, before ffmpeg was even spawned).
# Checked inside that wait loop so cancellation takes effect immediately
# rather than only after a process exists to kill.
_cancelled_hashes: set[str] = set()


# ─────────────────────────────────────────────────────────────
# File resolution
# ─────────────────────────────────────────────────────────────

def _largest_video_file(files: list) -> Optional[dict]:
    video_files = [
        f for f in files
        if f.get("name", "").lower().endswith(VIDEO_EXTENSIONS)
    ]
    return max(video_files, key=lambda f: f.get("size", 0), default=None)


def _resolve_file_entry(torrent_hash: str) -> Optional[dict]:
    """Like the old _resolve_file_path, but returns the full qBittorrent
    file entry (needed for piece_range/size), not just a path string."""
    torrent = get_torrent_info(torrent_hash)
    if not torrent:
        return None

    files = get_torrent_files(torrent_hash)
    if not files:
        return None

    return _largest_video_file(files)


def _resolve_file_path(torrent_hash: str) -> Optional[str]:
    torrent = get_torrent_info(torrent_hash)
    if not torrent:
        return None

    file_entry = _resolve_file_entry(torrent_hash)
    if not file_entry:
        return None

    return os.path.join(torrent["save_path"], file_entry["name"])


def _is_mkv(file_path: str) -> bool:
    return file_path.lower().endswith(".mkv")


# ─────────────────────────────────────────────────────────────
# Safe-prefix file feeder
#
# Reads only the confirmed-contiguous-downloaded prefix of the source file
# and writes it into a FIFO that ffmpeg reads from. This means ffmpeg never
# sees a read into a not-yet-downloaded region of a sparse/partial file --
# it just sees a pipe that blocks until more data is available, exactly
# like reading from a slow network socket. That's what eliminates the
# corruption / freeze-looping: ffmpeg was previously racing ahead into
# holes in the partially-downloaded file.
# ─────────────────────────────────────────────────────────────

class _SafeFileFeeder:
    def __init__(self, torrent_hash: str, file_path: str, file_entry: dict, fifo_path: str):
        self.torrent_hash = torrent_hash
        self.file_path = file_path
        self.file_entry = file_entry
        self.fifo_path = fifo_path
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.error: Optional[str] = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        try:
            self._feed_loop()
        except Exception as e:
            self.error = str(e)
            print(f"[stream] feeder error for {self.torrent_hash}: {e}")
        finally:
            with _active_feeders_lock:
                _active_feeders.pop(self.torrent_hash, None)

    def _feed_loop(self):
        file_size = self.file_entry.get("size", 0)
        bytes_written = 0
        last_progress_time = time.time()

        # Opening a FIFO for writing blocks until a reader (ffmpeg) opens
        # it for reading. ffmpeg is started right after the FIFO is
        # created, so this resolves quickly in practice.
        fifo_fd = os.open(self.fifo_path, os.O_WRONLY)

        try:
            with open(self.file_path, "rb") as src, os.fdopen(fifo_fd, "wb") as dst:
                while not self._stop_event.is_set() and bytes_written < file_size:
                    safe_bytes = get_safe_contiguous_bytes(self.torrent_hash, self.file_entry)

                    if safe_bytes <= bytes_written:
                        # No new contiguous data yet -- wait and re-check.
                        if time.time() - last_progress_time > STALL_TIMEOUT_SECONDS:
                            print(
                                f"[stream] download stalled for "
                                f"{self.torrent_hash}, no progress in "
                                f"{STALL_TIMEOUT_SECONDS}s, stopping feeder"
                            )
                            return
                        time.sleep(POLL_INTERVAL_SECONDS)
                        continue

                    last_progress_time = time.time()

                    chunk = src.read(safe_bytes - bytes_written)
                    if not chunk:
                        # Shouldn't normally happen since safe_bytes says
                        # this data exists on disk, but guard against a
                        # filesystem race anyway.
                        time.sleep(POLL_INTERVAL_SECONDS)
                        continue

                    dst.write(chunk)
                    dst.flush()
                    bytes_written += len(chunk)

        except BrokenPipeError:
            # ffmpeg exited (or was killed) and closed its end -- nothing
            # more to do.
            print(f"[stream] ffmpeg closed pipe for {self.torrent_hash}")
        finally:
            try:
                os.close(fifo_fd)
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────
# Background HLS Stream Engine (iPhone Safe)
# ─────────────────────────────────────────────────────────────

def _ensure_hls(torrent_hash: str, file_path: str, file_entry: dict) -> str:
    """
    Spawns an asynchronous FFmpeg worker that transcodes the stream into HLS.
    Uses libx264 (re-encode) for video and AAC stereo for audio, to
    guarantee playback compatibility on iOS/Safari.

    Crucially: ffmpeg never reads `file_path` directly. It reads from a
    FIFO that a feeder thread fills with only the confirmed-safe contiguous
    prefix of the source file (see _SafeFileFeeder above). This is what
    prevents corrupted/frozen output on partially-downloaded torrents.
    """
    output_dir = os.path.join(HLS_BASE_DIR, torrent_hash)
    os.makedirs(output_dir, exist_ok=True)

    playlist_path = os.path.join(output_dir, "index.m3u8")
    fifo_path = os.path.join(output_dir, "source.fifo")

    with _active_feeders_lock:
        already_running = torrent_hash in _active_feeders

    if not already_running:
        # Wait until enough contiguous data exists before starting ffmpeg
        # at all -- starting immediately on a near-empty file just means
        # ffmpeg's probe stalls or fails outright. Checked against
        # _cancelled_hashes on every iteration so a /cancelTorrent call
        # made while we're still in this "waiting for buffer" phase (i.e.
        # before ffmpeg has even started) takes effect immediately instead
        # of letting the wait run to completion first.
        for _ in range(120):  # up to ~60s
            if torrent_hash in _cancelled_hashes:
                raise HTTPException(status_code=409, detail="Stream was cancelled")
            safe_bytes = get_safe_contiguous_bytes(torrent_hash, file_entry)
            if safe_bytes >= min(MIN_INITIAL_SAFE_BYTES, file_entry.get("size", 0)):
                break
            time.sleep(0.5)

        # Recreate the FIFO fresh each time we (re)start the pipeline.
        if os.path.exists(fifo_path):
            os.remove(fifo_path)
        os.mkfifo(fifo_path)

        segment_type = "fmp4" if file_path.lower().endswith(".mp4") else "mpegts"
        print(f"[stream] Using segment type: {segment_type}")

        cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-fflags", "+genpts+discardcorrupt+igndts",
            "-err_detect", "ignore_err",
            "-analyzeduration", "100M",
            "-probesize", "100M",
            "-i", fifo_path,
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-c:v", "h264_nvenc",          # Changed: Swapped CPU encoder for NVIDIA NVENC GPU encoder
            "-preset", "p2",               # Changed: NVENC specific speed preset (p1=fastest, p7=slowest)
            "-rc", "vbr",                  # Changed: Sets rate control to Variable Bitrate
            "-cq", "21",                   # Changed: Replaced -crf with NVENC's Constant Quality
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ac", "2",
            "-f", "hls",
            "-hls_time", "4",
            "-hls_playlist_type", "event",
            "-hls_flags", "delete_segments+append_list",
            "-hls_segment_filename", os.path.join(output_dir, "seg_%04d.ts"),
            "-hls_segment_type", segment_type,
            playlist_path,
        ]
        """
        cmd = [
            "ffmpeg",
            "-loglevel", "error",
            "-fflags", "+genpts+discardcorrupt+igndts",
            "-err_detect", "ignore_err",
            "-analyzeduration", "100M",
            "-probesize", "100M",
            "-i", fifo_path,
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "21",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-ac", "2",
            "-f", "hls",
            "-hls_time", "4",
            "-hls_playlist_type", "event",
            "-hls_flags", "delete_segments+append_list",
            "-hls_segment_filename", os.path.join(output_dir, "seg_%04d.ts"),
            "-hls_segment_type", segment_type,
            playlist_path,
        ]
        """

        print(f"[stream] Starting HLS encoding pipeline for hash: {torrent_hash}")

        log_path = os.path.join(output_dir, "ffmpeg.log")
        log_file = open(log_path, "wb")
        process = subprocess.Popen(cmd, stdout=log_file, stderr=log_file)

        with _active_processes_lock:
            _active_processes[torrent_hash] = process

        feeder = _SafeFileFeeder(torrent_hash, file_path, file_entry, fifo_path)
        feeder.start()

        with _active_feeders_lock:
            _active_feeders[torrent_hash] = feeder

        # Race protection: briefly block until the initial .m3u8 index file
        # manifests, OR until it becomes clear ffmpeg has died.
        for _ in range(60):
            if os.path.exists(playlist_path) and os.path.getsize(playlist_path) > 0:
                break
            if process.poll() is not None:
                # ffmpeg exited before producing a playlist -- surface the
                # captured log instead of returning a path that will 500.
                try:
                    with open(log_path, "r", errors="replace") as f:
                        tail = f.read()[-2000:]
                except OSError:
                    tail = "(no ffmpeg log available)"
                raise HTTPException(
                    status_code=500,
                    detail=f"ffmpeg exited before producing HLS output: {tail}",
                )
            time.sleep(0.5)

    return playlist_path


def get_buffer_status(torrent_hash: str) -> dict:
    """
    Reports the real safe-streaming buffer for a torrent's chosen video
    file -- the same contiguous-piece check that gates ffmpeg startup in
    _ensure_hls -- so the frontend's "ready to play" signal and the
    backend's "I'm about to actually start ffmpeg" threshold are driven by
    the exact same number instead of two independently-guessed constants.

    Returns a dict the /torrentProgress endpoint can return more or less
    directly.
    """
    #print(f"[stream] Checking buffer status for torrent hash: {torrent_hash}")
    torrent = get_torrent_info(torrent_hash)
    if not torrent:
        return {
            "name": "",
            "safe_completed_mb": 0.0,
            "required_mb": MIN_INITIAL_SAFE_BYTES / (1024 * 1024),
            "ready": False,
            "status": "Fetching torrent info…",
        }

    file_entry = _resolve_file_entry(torrent_hash)
    if not file_entry:
        # Torrent exists but qBittorrent hasn't reported file metadata yet
        # (common in the first second or two right after adding a magnet).
        return {
            "name": torrent.get("name", ""),
            "safe_completed_mb": 0.0,
            "required_mb": MIN_INITIAL_SAFE_BYTES / (1024 * 1024),
            "ready": False,
            "status": "Reading torrent metadata…",
        }

    file_size = file_entry.get("size", 0)
    safe_bytes = get_safe_contiguous_bytes(torrent_hash, file_entry)
    required_bytes = min(MIN_INITIAL_SAFE_BYTES, file_size) if file_size else MIN_INITIAL_SAFE_BYTES
    #print(f"[stream] safe_bytes={safe_bytes}, required_bytes={required_bytes}, file_size={file_size}")
    return {
        "name": torrent.get("name", ""),
        "safe_completed_mb": safe_bytes / (1024 * 1024),
        "required_mb": required_bytes / (1024 * 1024),
        "ready": safe_bytes >= required_bytes,
        "status": "Downloading — please wait…",
    }


def cancel_stream(torrent_hash: str) -> None:
    """
    Tears down any in-progress or running HLS pipeline for this hash:
      - marks it cancelled so a wait loop still inside _ensure_hls's
        "waiting for initial buffer" phase exits immediately
      - stops the feeder thread
      - kills the ffmpeg process if one was started
      - removes the HLS output directory (playlist, segments, FIFO, log)

    Safe to call even if no pipeline was ever started for this hash (e.g.
    the user cancelled while the torrent was still being added).
    """
    _cancelled_hashes.add(torrent_hash)

    with _active_feeders_lock:
        feeder = _active_feeders.pop(torrent_hash, None)
    if feeder:
        feeder.stop()

    with _active_processes_lock:
        process = _active_processes.pop(torrent_hash, None)
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        except Exception as e:
            print(f"[stream] error terminating ffmpeg for {torrent_hash}: {e}")

    output_dir = os.path.join(HLS_BASE_DIR, torrent_hash)
    if os.path.isdir(output_dir):
        import shutil
        try:
            shutil.rmtree(output_dir)
        except OSError as e:
            print(f"[stream] error removing HLS output dir for {torrent_hash}: {e}")

    # Don't let _cancelled_hashes grow unbounded across the app's lifetime --
    # it only needs to suppress a wait loop that's already in flight right
    # now, so it's safe to drop once that's had time to observe it.
    def _expire():
        time.sleep(120)
        _cancelled_hashes.discard(torrent_hash)
    threading.Thread(target=_expire, daemon=True).start()


# ─────────────────────────────────────────────────────────────
# Public API Entrypoints (Called by main.py)
# ─────────────────────────────────────────────────────────────

def get_stream_response(torrent_hash: str, request: Request):
    """
    Responds to GET /stream/{torrent_hash}
    """
    file_entry = _resolve_file_entry(torrent_hash)
    if not file_entry:
        raise HTTPException(status_code=404, detail="Torrent file not found")

    torrent = get_torrent_info(torrent_hash)
    file_path = os.path.join(torrent["save_path"], file_entry["name"])

    playlist_path = _ensure_hls(torrent_hash, file_path, file_entry)
    if not os.path.exists(playlist_path):
        raise HTTPException(status_code=500, detail="Failed to initialize HLS stream container")

    return FileResponse(playlist_path, media_type="application/x-mpegURL")


def start_transcode_response(torrent_hash: str):
    """
    Responds to GET /stream/{torrent_hash}/prepare
    """
    file_entry = _resolve_file_entry(torrent_hash)
    print(f"[stream] Preparing HLS for torrent hash: {torrent_hash}, file: {file_entry and file_entry.get('name')}")
    if not file_entry:
        raise HTTPException(status_code=404, detail="Torrent file not found")

    torrent = get_torrent_info(torrent_hash)
    file_path = os.path.join(torrent["save_path"], file_entry["name"])

    playlist_path = _ensure_hls(torrent_hash, file_path, file_entry)
    if not os.path.exists(playlist_path):
        raise HTTPException(status_code=500, detail="Failed to parse transcode parameters")

    return {
        "status": "ready",
        "playlist": f"/stream/{torrent_hash}/hls/index.m3u8"
    }


def get_hls_segment(torrent_hash: str, filename: str):
    """
    Serves active playlist updates (.m3u8) and video stream segments (.ts)
    """
    segment_path = os.path.join(HLS_BASE_DIR, torrent_hash, filename)
    if not os.path.exists(segment_path):
        raise HTTPException(status_code=404, detail="Requested HLS resource not found")

    # FIX: Use strict, lowercase web-standard MIME types
    if filename.endswith(".m3u8"):
        media_type = "application/vnd.apple.mpegurl"  # Native Apple/Safari standard
    elif filename.endswith(".ts"):
        media_type = "video/mp2t"                     # Must be lowercase
    else:
        media_type = "application/octet-stream"

    return FileResponse(segment_path, media_type=media_type)


# ─────────────────────────────────────────────────────────────
# Subtitle extraction
# ─────────────────────────────────────────────────────────────

def get_subtitle_tracks(file_path: str) -> list[dict]:
    TEXT_CODECS = {"subrip", "ass", "ssa", "webvtt", "mov_text", "text"}

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "s",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        data = json.loads(result.stdout)
        tracks = []

        for stream in data.get("streams", []):
            codec = stream.get("codec_name", "").lower()
            if codec not in TEXT_CODECS:
                continue

            tags = stream.get("tags", {})
            tracks.append({
                "index": stream["index"],
                "language": tags.get("language", "und"),
                "title": tags.get(
                    "title",
                    tags.get("language", f"Track {len(tracks) + 1}")
                ),
            })

        return tracks

    except Exception as e:
        print(f"[stream] ffprobe subtitle error: {e}")
        return []


def extract_subtitle_as_vtt(file_path: str, stream_index: int) -> Optional[str]:
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-v", "quiet",
                "-i", file_path,
                "-map", f"0:{stream_index}",
                "-c:s", "webvtt",
                "-f", "webvtt",
                "pipe:1",
            ],
            capture_output=True,
            timeout=30,
        )

        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")

    except Exception as e:
        print(f"[stream] subtitle extract error: {e}")

    return None


# ─────────────────────────────────────────────────────────────
# Subtitles API
# ─────────────────────────────────────────────────────────────

def get_subtitle_tracks_response(torrent_hash: str) -> list[dict]:
    file_path = _resolve_file_path(torrent_hash)

    if not file_path or not _is_mkv(file_path):
        return []

    return get_subtitle_tracks(file_path)


def get_subtitle_vtt_response(torrent_hash: str, stream_index: int) -> PlainTextResponse:
    file_path = _resolve_file_path(torrent_hash)

    if not file_path:
        raise HTTPException(status_code=404, detail="Torrent file not found")

    vtt = extract_subtitle_as_vtt(file_path, stream_index)

    if not vtt:
        raise HTTPException(status_code=404, detail="Subtitle track not found")

    return PlainTextResponse(vtt, media_type="text/vtt")