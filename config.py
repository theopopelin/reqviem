import logging
import os
from urllib.parse import urlparse

import yt_dlp


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger("reqviem")

TOKEN = os.getenv("DISCORD_TOKEN_REQVIEM")

if not TOKEN:
    raise RuntimeError("missing DISCORD_TOKEN_REQVIEM env var.")


# Used to extract audio when a track starts playing.
YDL_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "skip_download": True,
}

# Used to retrieve playlist entries without downloading audio.
PLAYLIST_YDL_OPTIONS = {
    **YDL_OPTIONS,
    "noplaylist": False,
    "extract_flat": "in_playlist",
}


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def is_youtube_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())

        return (
            parsed.scheme in {"http", "https"}
            and parsed.hostname is not None
            and parsed.hostname.lower() in YOUTUBE_HOSTS
            and parsed.path not in {"", "/"}
        )
    except ValueError:
        return False


def extract_info(url: str) -> dict:
    """Extract a video's audio information for playback."""
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("Could not get info.")

    return info


def extract_playlist_info(url: str) -> dict:
    """Extract playlist metadata without downloading audio."""
    with yt_dlp.YoutubeDL(PLAYLIST_YDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)

        if not info:
            raise ValueError("Could not get playlist info.")

        if info.get("_type") in {"playlist", "multi_video"}:
            info["entries"] = list(info.get("entries") or [])

    return info