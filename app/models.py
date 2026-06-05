from pydantic import BaseModel
from typing import Optional


class TorrentLink(BaseModel):
    link: str


class TorrentResponse(BaseModel):
    success: bool
    message: str
    torrent_hash: Optional[str] = None
    vlc_opened: bool = False


class MagnetRequest(BaseModel):
    link: str