from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import os
import socket
from models import TorrentLink, TorrentResponse, MagnetRequest
from qb import *
from metadata import *
from tpb import *
from vlc import *
from stream import *  # Contains get_stream_response, start_transcode_response, get_hls_segment
from cleanup import *
import threading
import subprocess
import uvicorn

app = FastAPI()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTER_DIR = os.path.join(BASE_DIR, "../temp/posters/")
PAGES_DIR = os.path.join(BASE_DIR, "../frontend/templates/") 
STATIC_DIR = os.path.join(BASE_DIR, "../frontend/dist/")
STYLES_DIR = os.path.join(BASE_DIR, "../frontend/styles/")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/styles", StaticFiles(directory=STYLES_DIR), name="styles")
os.makedirs(POSTER_DIR, exist_ok=True)
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


def get_movie_posters():
    return get_trending_posters_movies()


def get_tv_posters():
    return get_trending_posters_tv()

    

# ─────────────────────────────────────────────────────────────
# PAGE ROUTES — serve static HTML shells, no server-side rendering.
# Each page's TS (client.ts / search.ts / movie.ts) fetches its own
# data from the /api/* routes below once the page loads.
# ─────────────────────────────────────────────────────────────

@app.get("/")
async def index_page():
    print(f"[index] Serving index page")
    return FileResponse(os.path.join(PAGES_DIR, "index.html"))


@app.get("/search/{query}")
async def search_page(query: str):
    # query is read client-side via window.location.pathname in search.ts —
    # the HTML shell itself is identical regardless of query.
    return FileResponse(os.path.join(PAGES_DIR, "search.html"))


@app.get("/movie/{id}")
async def movie_page(id: str):
    return FileResponse(os.path.join(PAGES_DIR, "movie.html"))

@app.get("/tv/{id}")
async def tv_page(id: str):
    return FileResponse(os.path.join(PAGES_DIR, "tv.html"))


# ─────────────────────────────────────────────────────────────
# JSON API — all data the TS fetches on each page
# ─────────────────────────────────────────────────────────────

@app.get("/api/posters")
async def api_posters():
    print(f"[api_posters] Refreshing poster cache and returning current posters")
    # Triggers a poster-cache refresh from trending movies, same as the
    # old index() route did, then returns the current poster filenames.
    return {
        "movies": get_movie_posters(),
        "tv": get_tv_posters()
    }

@app.get("/api/refresh")
async def api_refresh():
    print(f"[api_refresh] Refreshing poster cache")
    # Triggers a poster-cache refresh from trending movies, same as the
    # old index() route did, but doesn't return any data since the client
    # will fetch the updated poster list via /api/posters immediately after.
    download_posters(get_trending_movies())
    download_posters(get_trending_tv())
    return {"success": True}


@app.get("/api/search/{query}")
async def api_search(query: str):
    movies = search_movies(query)
    tv = search_tv(query)
    return {
        "movies": movies, 
        "tv": tv
    }


@app.get("/api/movie/{id}")
async def api_movie_detail(id: str):
    #movie = search_movie_by_id(id)
    #if not movie:
    #    raise HTTPException(status_code=404, detail="Movie not found on TMDB")
    #
    detail = get_movie_detail(id)
    downloadable_torrents = get_downloadable_torrents(detail["title"])
    detail["torrents"] = downloadable_torrents
    return detail


# ─────────────────────────────────────────────────────────────
# HLS STREAMING & PLAYBACK ROUTING
# ─────────────────────────────────────────────────────────────

@app.get("/stream/{torrent_hash}")
async def stream_video(torrent_hash: str, request: Request):
    return get_stream_response(torrent_hash, request)


@app.get("/stream/{torrent_hash}/prepare")
def prepare_stream(torrent_hash: str):
    print(f"[stream] Preparing HLS for torrent hash: {torrent_hash}")
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
    print(f"[interact_torrent] Received magnet link: {req.link}")
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

    Matches WipeResponse expected by client.ts:
      { status, torrents_removed, files_deleted, detail? }
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
            "torrents_removed": 0,
            "files_deleted": False,
            "detail": str(e)
        }


def get_tailscale_ip():
    return subprocess.check_output(
        ["tailscale", "ip", "-4"],
        text=True
    ).strip()

if __name__ == "__main__":
    ts_ip = get_tailscale_ip()

    print(f"UI: http://{ts_ip}:5000")

    uvicorn.run(
        app,
        host=ts_ip,
        port=5000,
    )