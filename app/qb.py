import os
import time
import subprocess
import requests
from dotenv import load_dotenv
from typing import Optional, Dict

load_dotenv()

QBITTORRENT_URL = os.getenv("QB_URL")
QB_USER = os.getenv("QB_USER")
QB_PASS = os.getenv("QB_PASS")
SAVE_PATH = os.getenv("SAVE_PATH")

_session = None


def get_session() -> Optional[requests.Session]:
    global _session

    if _session:
        return _session

    try:
        subprocess.Popen(["qbittorrent-nox"])
        time.sleep(2)

        session = requests.Session()

        r = session.post(
            f"{QBITTORRENT_URL}/api/v2/auth/login",
            data={"username": QB_USER, "password": QB_PASS},
            timeout=10
        )

        if r.status_code == 200 and r.text == "Ok.":
            _session = session
            return session

    except Exception as e:
        print("[qb] error:", e)

    return None


def add_magnet(magnet: str, sequential=True, paused=False) -> Dict:
    session = get_session()
    if not session:
        return {"success": False, "message": "No qBittorrent session"}

    r = session.post(
        f"{QBITTORRENT_URL}/api/v2/torrents/add",
        data={
            "urls": magnet,
            "sequentialDownload": str(sequential).lower(),
            "firstLastPiecePrio": str(sequential).lower(),
            "savepath": SAVE_PATH,
            "paused": str(paused).lower()
        }
    )

    if r.status_code == 200:
        return {"success": True, "message": "Added"}
    return {"success": False, "message": r.text}


def list_torrents():
    session = get_session()
    if not session:
        return []

    r = session.get(f"{QBITTORRENT_URL}/api/v2/torrents/info")
    return r.json() if r.status_code == 200 else []


def get_transfer_info():
    session = get_session()
    if not session:
        return {}

    r = session.get(f"{QBITTORRENT_URL}/api/v2/transfer/info")
    return r.json() if r.status_code == 200 else {}