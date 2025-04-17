from __future__ import annotations

import logging
import re
import textwrap
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

from aiohttp_socks import ProxyError
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt

from app.schema import VideoData

if TYPE_CHECKING:
    import aiohttp

logger = logging.getLogger("uvicorn")

ERROR_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta property="og:title" content="Error - Video Not Found">
  <meta property="og:description" content="{message}">
  <meta name="twitter:card" content="summary">
  <meta name="twitter:title" content="Error - Video Not Found">
  <meta name="twitter:description" content="{message}">
  <title>Error</title>
  <style>
    body {{
      font-family: sans-serif;
      background: #f9f9f9;
      color: #333;
      padding: 2rem;
    }}
  </style>
</head>
<body>
  <h1>Error</h1>
  <p>{message}</p>
</body>
</html>
"""


def remove_query_params(url: str) -> str:
    parsed_url = urlparse(url)
    return urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            "",
            parsed_url.fragment,
        )
    )


def extract_bvid(url: str) -> str | None:
    match = re.search(r"https://(?:www.|m.)?bilibili.com/video/([\w]+)", url)
    return match.group(1) if match else None


def get_error_html(message: str) -> str:
    return ERROR_HTML.format(message=message)


async def fetch_video_info(session: aiohttp.ClientSession, *, bvid: str) -> VideoData:
    logger.info("Fetching video info for %s", bvid)

    async with session.get(
        f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
        headers={"User-Agent": "Mozilla/5.0"},
    ) as resp:
        resp.raise_for_status()
        view_data: dict[str, Any] = await resp.json()

        if view_data.get("code") != 0:
            msg = view_data.get("message", "Invalid Bilibili video ID")
            raise ValueError(msg)

        return VideoData(**view_data["data"])


@retry(
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((ProxyError, TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.INFO),
    reraise=True,
)
async def fetch_video_url(session: aiohttp.ClientSession, *, bvid: str) -> str:
    logger.info("Fetching video URL for %s", bvid)

    async with session.get(f"https://api.injahow.cn/bparse/?bv={bvid}&q=64&otype=json") as resp:
        resp.raise_for_status()

        data = await resp.json()
        if data.get("code") != 0:
            msg = "Failed to retrieve video URL"
            raise ValueError(msg)

        return data["url"]


def get_embed_html(*, video: VideoData, current_url: str, video_url: str) -> str:
    image = video.pages[0].first_frame if video.pages else video.thumbnail
    image = image or video.thumbnail
    html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="utf-8">
        <meta name="theme-color" content="#0fa6d8">
        <meta property="og:title" content="{video.owner.name} - {video.title}">
        <meta property="og:type" content="video">
        <meta property="og:site_name" content="Bilibili | 👁️ {video.stats.views}">
        <meta property="og:url" content="{current_url}">
        <meta property="og:video" content="{video_url}">
        <meta property="og:video:secure_url" content="{video_url}">
        <meta property="og:video:type" content="video/mp4">
        <meta property="og:video:width" content={video.dimension.width}>
        <meta property="og:video:height" content={video.dimension.height}>
        <meta property="og:image" content="{image}">
        <meta name="twitter:card" content="player">
        <meta name="twitter:title" content="{video.title}">
        <meta name="twitter:description" content="{video.description}">
        <meta name="twitter:image" content="{image}">
        <meta name="twitter:player" content="{current_url}">
        <meta name="twitter:player:width" content={video.dimension.width}>
        <meta name="twitter:player:height" content={video.dimension.height}>
        <title>{video.title}</title>
        </head>
        </html>
    """
    return textwrap.dedent(html)
