import os
import time
import subprocess
import requests
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

QBITTORRENT_URL = os.getenv("QB_URL")
QB_USER = os.getenv("QB_USER")
QB_PASS = os.getenv("QB_PASS")
SAVE_PATH = os.getenv("SAVE_PATH")
TIMEOUT = 120
INTERVAL = 0.25

_session: Optional[requests.Session] = None


# ── Session ────────────────────────────────────────────────────────────────────

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
            timeout=10,
        )

        if r.status_code == 200 and r.text == "Ok.":
            _session = session
            return session

    except Exception as e:
        print(f"[qb] session error: {e}")

    return None


# ── Torrents ───────────────────────────────────────────────────────────────────

def add_magnet(magnet: str, paused: bool = False) -> dict:
    session = get_session()
    if not session:
        return {"success": False, "message": "No qBittorrent session"}

    r = session.post(
        f"{QBITTORRENT_URL}/api/v2/torrents/add",
        data={
            "urls": magnet,
            "sequentialDownload": "true",
            "firstLastPiecePrio": "false",
            "savepath": SAVE_PATH,
            "paused": str(paused).lower(),
        },
    )

    if r.status_code != 200:
        return {"success": False, "message": r.text}

    for t in range(TIMEOUT):
        torrent_hash = get_torrent_hash_by_magnet(session, magnet)
        if torrent_hash:
            break
        print(f"[qb] waiting for torrent hash... ({t + 1}/{TIMEOUT})")
        time.sleep(INTERVAL)

    if torrent_hash:
        _patch_piece_priority(session, torrent_hash)

    return {"success": True, "message": "Added"}


def _patch_piece_priority(session: requests.Session, torrent_hash: str) -> None:
    """Enable firstLastPiecePrio for MP4 torrents (sequential stays on)."""
    files = get_torrent_files(torrent_hash)
    if not files:
        return
    has_mp4 = any(f.get("name", "").lower().endswith(".mp4") for f in files)

    # Only enable firstLastPiecePrio if it's MP4 with no MKVs
    if has_mp4:
        session.post(
            f"{QBITTORRENT_URL}/api/v2/torrents/toggleFirstLastPiecePrio",
            data={"hashes": torrent_hash},
        )
        print(f"[qb] enabled firstLastPiecePrio for MP4 torrent {torrent_hash}")

def get_torrent_hash_by_magnet(session: requests.Session, magnet_link: str) -> Optional[str]:
    """Extract or find torrent hash from magnet link"""
    # Try to extract hash from magnet link
    import re
    hash_match = re.search(r'btih:([a-fA-F0-9]+)', magnet_link)
    if hash_match:
        #print("EXTRACTED HASH:", hash_match.group(1).lower())
        return hash_match.group(1).lower()

    # If not found, get the most recently added torrent
    try:
        response = session.get(f"{QBITTORRENT_URL}/api/v2/torrents/info", params={"limit": 1})
        if response.status_code == 200 and response.json():
            #print("RECENT HASH:", response.json()[0].get('hash'))
            return response.json()[0].get('hash')
    except:
        pass

    return None


def list_torrents() -> list:
    session = get_session()
    if not session:
        return []

    r = session.get(f"{QBITTORRENT_URL}/api/v2/torrents/info")
    return r.json() if r.status_code == 200 else []


def get_torrent_info(torrent_hash: str) -> Optional[dict]:
    """Return metadata dict for a single torrent, or None if not found."""
    session = get_session()
    if not session:
        return None

    r = session.get(
        f"{QBITTORRENT_URL}/api/v2/torrents/info",
        params={"hashes": torrent_hash},
    )
    if r.status_code == 200 and r.json():
        return r.json()[0]
    return None


def get_torrent_files(torrent_hash: str) -> Optional[list]:
    """Return the file list for a torrent, or None on failure."""
    session = get_session()
    if not session:
        return None

    r = session.get(
        f"{QBITTORRENT_URL}/api/v2/torrents/files",
        params={"hash": torrent_hash},
    )
    return r.json() if r.status_code == 200 else None


# ── Transfer ───────────────────────────────────────────────────────────────────

def get_transfer_info() -> dict:
    session = get_session()
    if not session:
        return {}

    r = session.get(f"{QBITTORRENT_URL}/api/v2/transfer/info")
    return r.json() if r.status_code == 200 else {}