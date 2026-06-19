import os
import re
import json
import subprocess
import time
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from qb import get_torrent_info, get_torrent_files

VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".wmv")

HLS_BASE_DIR = "/home/tpharmsen/Documents/autotorrent/temp/hls_streams/"
MP4_CACHE_DIR = "/home/tpharmsen/Documents/autotorrent/temp/remux_mp4/"

# Keep track of active background ffmpeg workers to prevent duplicates
_active_transcodes = {}

os.makedirs(HLS_BASE_DIR, exist_ok=True)

# ─────────────────────────────────────────────────────────────
# File resolution
# ─────────────────────────────────────────────────────────────

def _largest_video_file(files: list) -> Optional[dict]:
    video_files = [
        f for f in files
        if f.get("name", "").lower().endswith(VIDEO_EXTENSIONS)
    ]
    return max(video_files, key=lambda f: f.get("size", 0), default=None)


def _resolve_file_path(torrent_hash: str) -> Optional[str]:
    torrent = get_torrent_info(torrent_hash)
    if not torrent:
        return None

    files = get_torrent_files(torrent_hash)
    if not files:
        return None

    best = _largest_video_file(files)
    if not best:
        return None

    return os.path.join(torrent["save_path"], best["name"])


def _is_mkv(file_path: str) -> bool:
    return file_path.lower().endswith(".mkv")


# ─────────────────────────────────────────────────────────────
# Background HLS Stream Engine (iPhone Safe)
# ─────────────────────────────────────────────────────────────

def _ensure_hls(torrent_hash: str, file_path: str) -> str:
    """
    Spawns an asynchronous FFmpeg worker that transcodes the stream into HLS.
    Uses video stream copying (instant) and transcodes audio to stereo AAC 
    to guarantee flawless audio playback on iOS/Safari.
    """
    output_dir = os.path.join(HLS_BASE_DIR, torrent_hash)
    os.makedirs(output_dir, exist_ok=True)
    
    playlist_path = os.path.join(output_dir, "index.m3u8")

    # If already running and active, don't start another process
    #if torrent_hash in _active_transcodes:
    #    if _active_transcodes[torrent_hash].poll() is None:
    #        return playlist_path

    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        # Tolerate growing torrent contents safely
        "-fflags", "+genpts+discardcorrupt",
        "-err_detect", "ignore_err",
        "-i", file_path,
        
        # Video: Copy stream directly (Lightning fast, uses 0% CPU)
        "-c:v", "copy",
        
        # Audio: Transcode to AAC stereo (Required because iOS chokes on DTS/AC3 tracks)
        "-c:a", "aac",
        "-b:a", "128k",
        "-ac", "2",
        
        # HLS Format configuration
        "-f", "hls",
        "-hls_time", "4",               # 4-second file chunks
        "-hls_playlist_type", "event",  # Appends to playlist dynamically as file grows
        "-hls_segment_filename", os.path.join(output_dir, "seg_%03d.ts"),
        playlist_path
    ]

    print(f"[stream] Starting HLS encoding pipeline for hash: {torrent_hash}")
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _active_transcodes[torrent_hash] = process

    # Race protection: Brief block until the initial .m3u8 index file manifests
    for _ in range(30):
        if os.path.exists(playlist_path) and os.path.getsize(playlist_path) > 0:
            break
        time.sleep(0.5)
    print(">>> FOUND INDEX HLS FILE")
    return playlist_path


# ─────────────────────────────────────────────────────────────
# Public API Entrypoints (Called by main.py)
# ─────────────────────────────────────────────────────────────

def get_stream_response(torrent_hash: str, request: Request):
    """
    Responds to GET /stream/{torrent_hash}
    """
    file_path = _resolve_file_path(torrent_hash)
    if not file_path:
        raise HTTPException(status_code=404, detail="Torrent file not found")

    playlist_path = _ensure_hls(torrent_hash, file_path)
    if not os.path.exists(playlist_path):
        raise HTTPException(status_code=500, detail="Failed to initialize HLS stream container")

    return FileResponse(playlist_path, media_type="application/x-mpegURL")


def start_transcode_response(torrent_hash: str):
    """
    Responds to GET /stream/{torrent_hash}/prepare
    """
    file_path = _resolve_file_path(torrent_hash)
    print(f"[stream] Preparing HLS for torrent hash: {torrent_hash}, file: {file_path}")
    if not file_path:
        raise HTTPException(status_code=404, detail="Torrent file not found")

    playlist_path = _ensure_hls(torrent_hash, file_path)
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