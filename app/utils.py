from __future__ import annotations

import asyncio
import logging
import re
import textwrap
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

import aiohttp
from aiohttp_socks import ProxyError
from tenacity import before_sleep_log, retry, retry_if_exception_type, stop_after_attempt

from app.schema import VideoData, VideoURLRequest

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


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


def is_episode(url: str) -> bool:
    return "bilibili.com/bangumi/play" in url


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


async def fetch_episode_bvid(session: aiohttp.ClientSession, *, ep_id: str, episode: int) -> str:
    logger.info("Fetching episode bvid for %s", ep_id)

    async with session.get(
        f"https://api.bilibili.com/pgc/view/web/ep/list?ep_id={ep_id}",
        headers={"User-Agent": "Mozilla/5.0"},
    ) as resp:
        resp.raise_for_status()
        data: dict[str, Any] = await resp.json()
        episodes = data["result"]["episodes"]
        episode_data = episodes[episode - 1]
        return episode_data["bvid"]


@retry(
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type((ProxyError, TimeoutError)),
    before_sleep=before_sleep_log(logger, logging.INFO),
    reraise=True,
)
async def fetch_video_url(session: aiohttp.ClientSession, request: VideoURLRequest) -> str:
    logger.info("Fetching video URL with request: %s", request)

    api_url = "https://api.injahow.cn/bparse/"
    params = request.model_dump(exclude_unset=True)

    async with session.get(api_url, params=params) as resp:
        resp.raise_for_status()

        data = await resp.json()
        if data.get("code") != 0:
            logger.error("Failed to retrieve video URL: %s", data)
            msg = "Failed to retrieve video URL"
            raise ValueError(msg)

        return data["url"]


def get_embed_html(*, video: VideoData, current_url: str, video_url: str) -> str:
    image = video.pages[0].first_frame if video.pages else video.thumbnail
    image = image or video.thumbnail

    stats = video.stats
    site_name = f"👁️ {stats.views:,} 👍 {stats.likes:,} 🪙 {stats.coins:,} ⭐ {stats.favorites:,}"

    html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
        <meta charset="utf-8">
        <meta name="theme-color" content="#0fa6d8">
        <meta property="og:title" content="{video.owner.name} - {video.title}">
        <meta property="og:type" content="video">
        <meta property="og:site_name" content="{site_name}">
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


CHUNK_SIZE = 1024 * 1024  # 1MB chunks for streaming


async def video_stream_generator(url: str) -> AsyncGenerator[bytes]:
    headers = {"User-Agent": "Mozilla/5.0"}

    async with aiohttp.ClientSession() as session, session.get(url, headers=headers) as resp:
        if not resp.ok:
            logger.error("Error fetching video: %s", resp.status)
            yield b""
            return

        # Get content length for proper streaming
        content_length = resp.headers.get("Content-Length")
        content_type = resp.headers.get("Content-Type", "video/mp4")

        logger.info(
            "Streaming video: Content-Length: %s, Content-Type: %s", content_length, content_type
        )

        async for chunk in resp.content.iter_chunked(CHUNK_SIZE):
            if not chunk:
                break
            yield chunk
            await asyncio.sleep(0.01)
