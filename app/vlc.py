import os
import subprocess
import time
from typing import Optional

from qb import get_torrent_info, get_torrent_files

VIDEO_EXTENSIONS = (".mkv", ".mp4")
MIN_SIZE = 75 * 1024 * 1024
TIMEOUT = 120
INTERVAL = 0.25


def _largest_video_file(files: list) -> Optional[dict]:
    """Return the largest video file from a torrent file list, or None."""
    video_files = [
        f for f in files
        if f.get("name", "").lower().endswith(VIDEO_EXTENSIONS)
    ]
    return max(video_files, key=lambda f: f.get("size", 0), default=None)


def _switch_to_tv() -> None:
    """Reroute display output to the TV (HDMI-A-1) and disable the monitor."""
    subprocess.run(["kscreen-doctor", "output.DP-3.disable", "output.HDMI-A-1.enable"])


def open_in_vlc(torrent_hash: str, switch_display: bool = True) -> bool:
    """
    Find the largest video file in a torrent and open it fullscreen in VLC.

    Args:
        torrent_hash:   qBittorrent hash of the torrent.
        switch_display: When True, switches the active display to HDMI-A-1
                        before launching VLC (default: True).

    Returns:
        True if VLC was launched successfully, False otherwise.
    """
    

    torrent = get_torrent_info(torrent_hash)
    if not torrent:
        print(f"[vlc] torrent not found: {torrent_hash}")
        return False

    for t in range(TIMEOUT):
        files = get_torrent_files(torrent_hash)
        if files:
            break
        print(f"[vlc] waiting for torrent files... ({t + 1}/{TIMEOUT})")
        time.sleep(INTERVAL)
    if not files:
        print("[vlc] no files found in torrent")
        return False

    best = _largest_video_file(files)
    if not best:
        print("[vlc] no playable video files found")
        return False
    
    try:
        #if switch_display:
        #    _switch_to_tv()
        best = _largest_video_file(files)
        for i in range(TIMEOUT):
            torrent = get_torrent_info(torrent_hash)
            if torrent['completed'] >= MIN_SIZE:
                break
            time.sleep(INTERVAL)
        
        file_path = os.path.join(torrent["save_path"], best["name"])
        #print(f"[vlc] opening: {file_path}")
        """
        subprocess.run([
            "vlc",
            "-f",
            "--sub-language", "eng",
            str(file_path)
        ])
        """
        return True
    except Exception as e:
        print(f"[vlc] error launching VLC: {e}")
        return False