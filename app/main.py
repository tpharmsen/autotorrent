from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os
import socket
from pathlib import Path
from models import TorrentLink, TorrentResponse, MagnetRequest
from qb import *
from metadata import *
from tpb import *
from vlc import *
from stream import * # Contains get_stream_response, start_transcode_response, get_hls_segment
from cleanup import *
import threading

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTER_DIR = os.path.join(BASE_DIR, "../temp/posters/")
STATIC_DIR = os.path.join(BASE_DIR, "../static/")
TEMPLATE_DIR = os.path.join(BASE_DIR, "../templates")

os.makedirs(POSTER_DIR, exist_ok=True)

templates = Jinja2Templates(Path(TEMPLATE_DIR))
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/posters", StaticFiles(directory=POSTER_DIR), name="posters")


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def get_posters():
    return sorted(
        f for f in os.listdir(POSTER_DIR)
        if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    trending = get_trending_movies()
    download_posters(trending)
    posters = get_posters()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "posters": posters,
        "trending": trending
    })


@app.get("/search/{query}", response_class=HTMLResponse)
async def movie_search(request: Request, query: str):
    movies = search_movies(query)
    #print(f"[search] Found {len(movies)} results for query '{query}'")
    print(movies[0].keys())
    return templates.TemplateResponse(
        "search.html",
        {"request": request, "movies": movies}
    )

@app.get("/movie/{title}", response_class=HTMLResponse)
async def movie_detail(request: Request, title: str):
    movie = search_movie(title)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found on TMDB")

    detail = get_movie_detail(movie["id"])
    downloadable_torrents = get_downloadable_torrents(detail["title"])
    detail["torrents"] = downloadable_torrents
    return templates.TemplateResponse("movie.html", {
        "request": request,
        "movie": detail
    })


# ─────────────────────────────────────────────────────────────
# HLS STREAMING & PLAYBACK ROUTING
# ─────────────────────────────────────────────────────────────

@app.get("/stream/{torrent_hash}")
async def stream_video(torrent_hash: str, request: Request):
    return get_stream_response(torrent_hash, request)


@app.get("/stream/{torrent_hash}/prepare")
def prepare_stream(torrent_hash: str):
    return start_transcode_response(torrent_hash)


@app.get("/stream/{torrent_hash}/hls/{filename}")
def hls_segment(torrent_hash: str, filename: str):
    return get_hls_segment(torrent_hash, filename)


# ─────────────────────────────────────────────────────────────
# SUBTITLES ENDPOINTS
# ─────────────────────────────────────────────────────────────

@app.get("/subtitleTracks/{torrent_hash}")
async def subtitle_tracks(torrent_hash: str):
    return get_subtitle_tracks_response(torrent_hash)


@app.get("/subtitles/{torrent_hash}/{stream_index}")
async def subtitle_vtt(torrent_hash: str, stream_index: int):
    return get_subtitle_vtt_response(torrent_hash, stream_index)


# ─────────────────────────────────────────────────────────────
# TORRENT CONTROLLERS
# ─────────────────────────────────────────────────────────────

@app.post("/interactTorrent")
async def interact_torrent(req: MagnetRequest):
    magnet = req.link
    add_result = add_magnet(magnet)
    if not add_result["success"]:
        raise HTTPException(status_code=500, detail=add_result["message"])

    torrent_hash = get_torrent_hash_by_magnet(get_session(), magnet)
    if not torrent_hash:
        raise HTTPException(status_code=500, detail="Failed to retrieve torrent hash")

    threading.Thread(target=open_in_vlc, args=(torrent_hash,), daemon=True).start()

    return {"success": True, "hash": torrent_hash}


@app.get("/torrentProgress")
async def torrent_progress(hash: str):
    torrent = get_torrent_info(hash)
    if not torrent:
        return {"name": "", "completed_mb": 0, "status": "Fetching torrent info…"}
    return {
        "name": torrent["name"],
        "completed_mb": torrent["completed"] / 1024 / 1024,
        "status": "Downloading — please wait…"
    }


@app.delete("/admin/wipe-all")
async def wipe_all(delete_files: bool = True):
    """
    FULL RESET:
    - qBittorrent torrents
    - downloaded files (optional)
    - HLS cache
    """

    try:
        success, torrent_count = wipe_all_qbittorrent(delete_files=delete_files)
        print(f"[cleanup] Wiped {torrent_count} torrents from qBittorrent (delete_files={delete_files})")
        wipe_all_hls()
        print(f"[cleanup] Wiped HLS cache")

        return {
            "status": success,
            "torrents_removed": torrent_count,
            "files_deleted": delete_files
        }

    except Exception as e:
        return {
            "status": "error",
            "detail": str(e)
        }
    
if __name__ == "__main__":
    import uvicorn
    ip = get_local_ip()
    print(f" UI: http://{ip}:5000")
    
    uvicorn.run(app, host="0.0.0.0", port=5000)