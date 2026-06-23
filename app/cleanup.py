import os
import shutil
import threading

from qb import get_session, list_torrents, delete_torrent

from vars import HLS_BASE_DIR

def wipe_all_qbittorrent(delete_files: bool = True):
    """
    Removes ALL torrents from qBittorrent.
    """
    session = get_session()

    torrents = list_torrents()
    print(f"[cleanup] Found {len(torrents)} torrents in qBittorrent for removal.")

    if not torrents:
        return 0
    #print(torrents[0].keys())
    hashes = [t['hash'] for t in torrents]
    success = delete_torrent(
        torrent_hash="|".join(hashes),
        delete_files=delete_files
    )

    return success, len(hashes)


def wipe_all_hls():
    """
    Deletes entire HLS cache directory.
    """
    files_removed = 0
    if os.path.exists(HLS_BASE_DIR):
        for root, dirs, files in os.walk(HLS_BASE_DIR):
            for filename in files:
                filepath = os.path.join(root, filename)
                os.remove(filepath)
                files_removed += 1
        shutil.rmtree(HLS_BASE_DIR, ignore_errors=True)
        os.makedirs(HLS_BASE_DIR, exist_ok=True)
    return files_removed
