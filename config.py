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

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "skip_download": True,
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
    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("Could not get info.")

    return info
