from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
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
from stream import *
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

@app.get("/stream/{torrent_hash}")
async def stream_video(torrent_hash: str, request: Request):
    return get_stream_response(torrent_hash, request)

@app.get("/subtitleTracks/{torrent_hash}")
async def subtitle_tracks(torrent_hash: str):
    return get_subtitle_tracks_response(torrent_hash)

@app.get("/subtitles/{torrent_hash}/{stream_index}")
async def subtitle_vtt(torrent_hash: str, stream_index: int):
    return get_subtitle_vtt_response(torrent_hash, stream_index)

"""
@app.post("/interactTorrent")
async def interact_torrent(req: MagnetRequest):
    magnet = req.magnet

    add_result = add_magnet(magnet)
    if not add_result["success"]:
        raise HTTPException(status_code=500, detail=add_result["message"])

    torrent_hash = get_torrent_hash_by_magnet(get_session(), magnet)
    if not torrent_hash:
        raise HTTPException(status_code=500, detail="Failed to retrieve torrent hash")

    vlc_result = open_in_vlc(torrent_hash)
    if not vlc_result:
        raise HTTPException(status_code=500, detail="Failed to open torrent in VLC")

    return {"success": True, "message": "Torrent added"}
"""
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
    #print("TORRENT INFO:", torrent["completed"] / 1024 / 1024)
    if not torrent:
        return {"name": "", "completed_mb": 0, "status": "Fetching torrent info…"}
    return {
        "name": torrent["name"],
        "completed_mb": torrent["completed"] / 1024 / 1024,
        "status": "Downloading — please wait…"
    }

"""

@app.post("/add", response_model=TorrentResponse)
async def add_torrent(torrent: TorrentLink):
    if not torrent.link.startswith("magnet:"):
        raise HTTPException(status_code=400, detail="Invalid magnet link")
    result = add_magnet(torrent.link)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    return TorrentResponse(success=True, message="Torrent added", torrent_hash=None, vlc_opened=False)


@app.get("/torrents")
async def torrents():
    all_torrents = list_torrents()
    return [t for t in all_torrents if t["state"] != "missingFiles"]

@app.get("/transfer-info")
async def transfer():
    info = get_transfer_info()
    return {
        "download_mb_s": info.get("dl_info_speed", 0) / 1024 / 1024,
        "upload_mb_s": info.get("up_info_speed", 0) / 1024 / 1024,
        "downloaded_gb": info.get("dl_info_data", 0) / 1024 / 1024 / 1024,
        "uploaded_gb": info.get("up_info_data", 0) / 1024 / 1024 / 1024,
        "ratio": info.get("global_ratio", 0)
    }

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/fetch-remote")
async def fetch_remote():
    from app.tpb import fetch_remote
    return fetch_remote()

"""

if __name__ == "__main__":
    # make sure poster directory exists
    import uvicorn
    ip = get_local_ip()
    print(f" UI: http://{ip}:5000")
    uvicorn.run(app, host="0.0.0.0", port=5000)