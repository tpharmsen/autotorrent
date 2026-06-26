import os
import time
import subprocess
import requests
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

from vars import QB_URL, QB_USER, QB_PASS, QB_SAVE_PATH
TIMEOUT = 120
INTERVAL = 0.25

_session: Optional[requests.Session] = None


# ── Session ────────────────────────────────────────────────────────────────────

def wait_for_qbittorrent(session: requests.Session, timeout=15):
    """
    Waits until qBittorrent WebUI is ready.
    """
    start = time.time()

    while time.time() - start < timeout:
        try:
            r = session.get(QB_URL, timeout=2)

            if r.status_code == 200:
                return True

        except requests.exceptions.RequestException:
            pass

        time.sleep(0.25)

    return False


def login_qbittorrent(session: requests.Session) -> bool:
    r = session.post(
        QB_URL + "/api/v2/auth/login",
        data={"username": QB_USER, "password": QB_PASS},
        timeout=5,
    )
    return r.status_code == 200 and r.text == "Ok."


def get_session():
    global _session

    if _session:
        return _session

    try:
        subprocess.Popen(["qbittorrent-nox"])

        session = requests.Session()

        # 🔥 wait until WebUI is alive (NO fixed sleep)
        if not wait_for_qbittorrent(session):
            print("[qb] WebUI did not start in time")
            return None

        # 🔐 login
        if login_qbittorrent(session):
            _session = session
            print("[qb] logged in to qBittorrent WebUI")
            return session

        print("[qb] login failed")

    except Exception as e:
        print(f"[qb] session error: {e}")

    return None

# ── Torrents ───────────────────────────────────────────────────────────────────

def add_magnet(magnet: str, paused: bool = False) -> dict:
    session = get_session()
    if not session:
        return {"success": False, "message": "No qBittorrent session"}

    r = session.post(
        f"{QB_URL}/api/v2/torrents/add",
        data={
            "urls": magnet,
            "sequentialDownload": "true",
            "firstLastPiecePrio": "false",
            "savepath": QB_SAVE_PATH,
            "paused": str(paused).lower(),
        },
    )

    if r.status_code != 200:
        return {"success": False, "message": r.text}

    for t in range(TIMEOUT):
        torrent_hash = get_torrent_hash_by_magnet(session, magnet)
        if torrent_hash:
            break
        time.sleep(INTERVAL)

    if torrent_hash:
        print(f"[qb] toggling piece priority for: {torrent_hash}")
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
            f"{QB_URL}/api/v2/torrents/toggleFirstLastPiecePrio",
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
        response = session.get(f"{QB_URL}/api/v2/torrents/info", params={"limit": 1})
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

    r = session.get(f"{QB_URL}/api/v2/torrents/info")
    return r.json() if r.status_code == 200 else []


def get_torrent_info(torrent_hash: str) -> Optional[dict]:
    """Return metadata dict for a single torrent, or None if not found."""
    session = get_session()
    if not session:
        return None

    r = session.get(
        f"{QB_URL}/api/v2/torrents/info",
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
        f"{QB_URL}/api/v2/torrents/files",
        params={"hash": torrent_hash},
    )
    return r.json() if r.status_code == 200 else None

def delete_torrent(torrent_hash: str, delete_files: bool = True) -> bool:
    """Delete a torrent by hash. Returns True if successful."""
    session = get_session()
    if not session:
        return False

    r = session.post(
        f"{QB_URL}/api/v2/torrents/delete",
        data={"hashes": torrent_hash, "deleteFiles": str(delete_files).lower()},
    )
    return r.status_code == 200


# ── Transfer ───────────────────────────────────────────────────────────────────

def get_transfer_info() -> dict:
    session = get_session()
    if not session:
        return {}

    r = session.get(f"{QB_URL}/api/v2/transfer/info")
    return r.json() if r.status_code == 200 else {}


def get_torrent_properties(torrent_hash: str) -> Optional[dict]:
    """Return generic torrent properties (includes piece_size), or None."""
    session = get_session()
    if not session:
        return None

    r = session.get(
        f"{QB_URL}/api/v2/torrents/properties",
        params={"hash": torrent_hash},
    )
    return r.json() if r.status_code == 200 else None


def get_piece_states(torrent_hash: str) -> Optional[list]:
    """Return the list of piece states (0=not downloaded, 1=downloading,
    2=downloaded) in piece order, or None on failure."""
    session = get_session()
    if not session:
        return None

    r = session.get(
        f"{QB_URL}/api/v2/torrents/pieceStates",
        params={"hash": torrent_hash},
    )
    return r.json() if r.status_code == 200 else None


def get_safe_contiguous_bytes(torrent_hash: str, file_entry: dict) -> int:
    piece_range = file_entry.get("piece_range")
    file_size = file_entry.get("size", 0)

    if not piece_range or file_size <= 0:
        return 0

    start_piece, end_piece = piece_range

    props = get_torrent_properties(torrent_hash)
    if not props:
        return 0
    piece_size = props.get("piece_size", 0)
    if piece_size <= 0:
        return 0

    states = get_piece_states(torrent_hash)
    if not states or end_piece >= len(states):
        return 0

    contiguous_complete_pieces = 0
    for piece_index in range(start_piece, end_piece + 1):
        #print(f"[get_safe_contiguous_bytes] piece_index: {piece_index}, state: {states[piece_index]}")
        if states[piece_index] == 2:
            contiguous_complete_pieces += 1
        #elif states[piece_index] == 1:
        #    contiguous_complete_pieces += 0.5
        else:
            break

    if contiguous_complete_pieces == 0:
        return 0

    safe_bytes = contiguous_complete_pieces * piece_size
    return min(safe_bytes, file_size)