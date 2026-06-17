import os
import re
import json
import subprocess
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse

from qb import get_torrent_info, get_torrent_files

VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".wmv")
FFMPEG_THREADS = "0"  # 0 = let ffmpeg use all available cores


# ── File resolution ────────────────────────────────────────────────────────────

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


def _parse_range(range_header: Optional[str], file_size: int) -> tuple[int, int]:
    if not range_header:
        return 0, file_size - 1
    match = re.match(r"bytes=(\d+)-(\d*)", range_header)
    if not match:
        return 0, file_size - 1
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else file_size - 1
    return start, min(end, file_size - 1)


# ── Subtitle extraction ────────────────────────────────────────────────────────

def get_subtitle_tracks(file_path: str) -> list[dict]:
    """
    Use ffprobe to list all subtitle streams in the file.
    Returns a list of dicts with: index, language, title.
    Only includes text-based formats browsers can handle after WebVTT conversion
    (subrip, ass, ssa, webvtt, mov_text). Bitmap formats like PGS/VOBSUB are
    skipped — they require image rendering which can't be done in the browser.
    """
    TEXT_CODECS = {"subrip", "ass", "ssa", "webvtt", "mov_text", "text"}

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams",
                "-select_streams", "s",  # subtitle streams only
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
                continue  # skip PGS, VOBSUB bitmap subtitles
            tags = stream.get("tags", {})
            tracks.append({
                "index": stream["index"],      # ffmpeg stream index (e.g. 3)
                "language": tags.get("language", "und"),
                "title": tags.get("title", tags.get("language", f"Track {len(tracks) + 1}")),
            })
        return tracks
    except Exception as e:
        print(f"[stream] ffprobe subtitle error: {e}")
        return []


def extract_subtitle_as_vtt(file_path: str, stream_index: int) -> Optional[str]:
    """
    Extract a single subtitle track from the file and return it as a
    WebVTT string. ffmpeg maps by absolute stream index and converts to vtt.
    Result is returned as a string (served inline, no temp files needed).
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-v", "quiet",
                "-i", file_path,
                "-map", f"0:{stream_index}",  # pick exact stream by index
                "-c:s", "webvtt",             # convert to WebVTT
                "-f", "webvtt",
                "pipe:1",                     # output to stdout
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0:
            return result.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[stream] subtitle extract error: {e}")
    return None


# ── MP4 streaming ──────────────────────────────────────────────────────────────

def _stream_mp4(file_path: str, request: Request) -> StreamingResponse:
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")
    start, end = _parse_range(range_header, file_size)
    length = end - start + 1

    def iter_file(path: str, offset: int, size: int, chunk: int = 1024 * 512):
        with open(path, "rb") as f:
            f.seek(offset)
            remaining = size
            while remaining > 0:
                data = f.read(min(chunk, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    status = 206 if range_header else 200
    headers = {
        "Content-Range": f"bytes {start}-{end}/{file_size}",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Type": "video/mp4",
    }
    return StreamingResponse(
        iter_file(file_path, start, length),
        status_code=status,
        headers=headers,
        media_type="video/mp4",
    )


# ── MKV → MP4 transcoding stream ──────────────────────────────────────────────

def _stream_mkv_transcode(file_path: str, request: Request) -> StreamingResponse:
    """
    Transcode MKV to H.264/AAC MP4 on the fly.
    Subtitles are NOT embedded in the video stream — they are served separately
    via /subtitles/<hash>/<index> and rendered by the browser's native track API.
    This keeps the transcode fast (video copy when possible) and lets the user
    toggle subtitles on/off without re-requesting the stream.
    """
    range_header = request.headers.get("range")
    seek_seconds = 0
    if range_header:
        match = re.match(r"bytes=(\d+)-", range_header)
        if match:
            # Rough byte-to-time conversion for seek; not frame-accurate but
            # good enough for scrubbing since we can't do true byte seeks on
            # a transcoded stream.
            start_byte = int(match.group(1))
            seek_seconds = start_byte // (1024 * 1024 * 2)  # ~2 MB/s estimate

    cmd = [
        "ffmpeg",
        "-loglevel", "error",
    ]
    if seek_seconds > 0:
        cmd += ["-ss", str(seek_seconds)]
    cmd += [
        "-i", file_path,
        "-map", "0:v:0",         # first video stream
        "-map", "0:a:0",         # first audio stream (subtitles handled separately)
        "-c:v", "copy",          # copy video — no re-encode if already H.264
        "-c:a", "aac",
        "-b:a", "192k",
        "-threads", FFMPEG_THREADS,
        "-movflags", "frag_keyframe+empty_moov+faststart",
        "-f", "mp4",
        "pipe:1",
    ]

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def iter_transcode(chunk: int = 1024 * 512):
        try:
            while True:
                data = process.stdout.read(chunk)
                if not data:
                    break
                yield data
        finally:
            process.kill()
            process.wait()

    headers = {
        "Accept-Ranges": "none",
        "Content-Type": "video/mp4",
        "X-Content-Type-Options": "nosniff",
    }
    return StreamingResponse(iter_transcode(), status_code=200, headers=headers, media_type="video/mp4")


# ── Public endpoint handlers ───────────────────────────────────────────────────

def get_stream_response(torrent_hash: str, request: Request) -> StreamingResponse:
    file_path = _resolve_file_path(torrent_hash)
    if not file_path:
        raise HTTPException(status_code=404, detail="Torrent file not found")
    if _is_mkv(file_path):
        return _stream_mkv_transcode(file_path, request)
    return _stream_mp4(file_path, request)


def get_subtitle_tracks_response(torrent_hash: str) -> list[dict]:
    """Return list of available subtitle tracks for the frontend to build <track> elements."""
    file_path = _resolve_file_path(torrent_hash)
    if not file_path or not _is_mkv(file_path):
        return []
    return get_subtitle_tracks(file_path)


def get_subtitle_vtt_response(torrent_hash: str, stream_index: int) -> PlainTextResponse:
    """Extract and serve a single subtitle track as WebVTT."""
    file_path = _resolve_file_path(torrent_hash)
    if not file_path:
        raise HTTPException(status_code=404, detail="Torrent file not found")
    vtt = extract_subtitle_as_vtt(file_path, stream_index)
    if not vtt:
        raise HTTPException(status_code=404, detail="Subtitle track not found or not extractable")
    return PlainTextResponse(vtt, media_type="text/vtt")