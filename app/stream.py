import os
import re
import json
import subprocess
import time
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse

from qb import get_torrent_info, get_torrent_files

VIDEO_EXTENSIONS = (".mkv", ".mp4", ".avi", ".mov", ".wmv")

HLS_BASE_DIR = "/home/tpharmsen/Documents/autotorrent/temp/hls_streams/"
MP4_CACHE_DIR = "/home/tpharmsen/Documents/autotorrent/temp/remux_mp4/"

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
# MP4 direct stream (iPhone-safe)
# ─────────────────────────────────────────────────────────────

def _stream_mp4(file_path: str, request: Request) -> StreamingResponse:
    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")

    start, end = 0, file_size - 1

    if range_header:
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if match:
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else file_size - 1

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

    headers = {
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
    }

    if range_header:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    return StreamingResponse(
        iter_file(file_path, start, length),
        status_code=206 if range_header else 200,
        headers=headers,
        media_type="video/mp4",
    )


# ─────────────────────────────────────────────────────────────
# MKV → MP4 REMUX (FAST)
# ─────────────────────────────────────────────────────────────

def _remux_mkv_to_mp4(file_path: str, torrent_hash: str) -> str:
    """
    Remux MKV → MP4 without re-encoding.
    """

    output_dir = os.path.join(MP4_CACHE_DIR, torrent_hash)
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, "video.mp4")

    # reuse if already exists
    if os.path.exists(output_path):
        return output_path

    cmd = [
        "ffmpeg",
        "-loglevel", "error",
        "-i", file_path,
        "-c", "copy",
        #"-movflags", "+faststart",
        output_path,
    ]

    print(f"[stream] remuxing MKV → MP4: {output_path}")
    subprocess.Popen(cmd)

    # wait until file is usable
    for _ in range(60):
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1024 * 1024:
            break
        time.sleep(0.5)

    return output_path


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def get_stream_response(torrent_hash: str, request: Request):
    file_path = _resolve_file_path(torrent_hash)

    if not file_path:
        raise HTTPException(status_code=404, detail="Torrent file not found")

    if _is_mkv(file_path):
        mp4_path = _remux_mkv_to_mp4(file_path, torrent_hash)
        return _stream_mp4(mp4_path, request)

    return _stream_mp4(file_path, request)


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