from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import os
import socket

from app.models import TorrentLink, TorrentResponse
from app.qb import add_magnet, list_torrents, get_transfer_info
from app.scraper import fetch_remote

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "../templates"))

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(BASE_DIR, "../static")),
    name="static"
)


def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    with open(os.path.join(BASE_DIR, "../templates/index.html")) as f:
        html = f.read()

    return HTMLResponse(html)


@app.post("/add", response_model=TorrentResponse)
async def add_torrent(torrent: TorrentLink):

    if not torrent.link.startswith("magnet:"):
        raise HTTPException(status_code=400, detail="Invalid magnet link")

    result = add_magnet(torrent.link)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])

    return TorrentResponse(
        success=True,
        message="Torrent added",
        torrent_hash=None,
        vlc_opened=False
    )


@app.get("/torrents")
async def torrents():
    all_torrents = list_torrents()
    relevent_torrents = [t for t in all_torrents if t['state'] != 'missingFiles']
    return relevent_torrents


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
    from app.scraper import fetch_remote
    items = fetch_remote()
    #print(f"Fetched {len(items)} items from remote source.")
    return items
    

# -------------------------
# Run
# -------------------------

if __name__ == "__main__":
    import uvicorn

    ip = get_local_ip()

    print("\n============================")
    print(" Torrent Dashboard Running")
    print("============================")
    print(f" UI: http://{ip}:5000")
    print(f" API: http://{ip}:5000/docs")
    print("============================\n")

    uvicorn.run(app, host="0.0.0.0", port=5000)