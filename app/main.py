from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import fastapi
from aiohttp_client_cache.backends.sqlite import SQLiteBackend
from aiohttp_client_cache.session import CachedSession
from aiohttp_socks import ProxyConnector
from dotenv import load_dotenv

from .utils import (
    extract_bvid,
    fetch_video_info,
    fetch_video_url,
    get_embed_html,
    get_error_html,
    remove_query_params,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

load_dotenv()
logger = logging.getLogger("uvicorn")


@asynccontextmanager
async def app_lifespan(app: fastapi.FastAPI) -> AsyncGenerator[None, None]:
    cache = SQLiteBackend(cache_name="cache.db", expire_after=3600)
    proxy_url = os.getenv("PROXY_URL")
    logger.info("Proxy detected: %s", proxy_url is not None)

    app.state.session = CachedSession(cache=cache)
    app.state.proxy_session = CachedSession(
        cache=cache, connector=ProxyConnector.from_url(proxy_url) if proxy_url else None
    )

    try:
        yield
    finally:
        await app.state.session.close()
        await app.state.proxy_session.close()


app = fastapi.FastAPI(lifespan=app_lifespan)


@app.exception_handler(fastapi.HTTPException)
def http_exception_handler(
    _: fastapi.Request, exc: fastapi.HTTPException
) -> fastapi.responses.HTMLResponse:
    logger.error("HTTP error: %s - %s", exc.status_code, exc.detail)
    return fastapi.responses.HTMLResponse(get_error_html(exc.detail))


@app.exception_handler(Exception)
def exception_handler(_: fastapi.Request, exc: Exception) -> fastapi.responses.HTMLResponse:
    logger.error("Unhandled exception: %s", exc)
    return fastapi.responses.HTMLResponse(get_error_html(str(exc)))


@app.get("/")
async def index() -> fastapi.responses.RedirectResponse:
    return fastapi.responses.RedirectResponse("https://github.com/seriaati/fxBilibili")


@app.get("/favicon.ico")
async def favicon() -> fastapi.responses.Response:
    return fastapi.responses.Response(status_code=204)


@app.get("/dl/{bvid}")
async def download_bilibili_video(bvid: str) -> fastapi.responses.Response:
    video_url = await fetch_video_url(app.state.proxy_session, bvid=bvid)
    return fastapi.responses.RedirectResponse(video_url)


@app.get("/dl/b23/{vid}")
async def download_b23_video(vid: str) -> fastapi.responses.Response:
    async with app.state.session.get(f"https://b23.tv/{vid}") as resp:
        final_url = str(resp.url)

    bvid = extract_bvid(remove_query_params(final_url))
    if bvid is None:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail="Invalid Bilibili URL"
        )

    video_url = await fetch_video_url(app.state.proxy_session, bvid=bvid)
    return fastapi.responses.RedirectResponse(video_url)


async def bilibili_embed(request: fastapi.Request, bvid: str) -> fastapi.responses.Response:
    session: CachedSession = app.state.session
    proxy_session: CachedSession = app.state.proxy_session

    video = await fetch_video_info(session, bvid=bvid)
    video_url = await fetch_video_url(proxy_session, bvid=bvid)

    html = get_embed_html(video=video, current_url=str(request.url), video_url=video_url)
    return fastapi.responses.HTMLResponse(html)


@app.get("/b23/{vid}")
async def embed_b23_video(request: fastapi.Request, vid: str) -> fastapi.responses.Response:
    url = f"https://b23.tv/{vid}"

    if "Discordbot" not in request.headers.get("User-Agent", ""):
        return fastapi.responses.RedirectResponse(url)

    session: CachedSession = app.state.session
    async with session.get(url) as resp:
        final_url = str(resp.url)

    bvid = extract_bvid(remove_query_params(final_url))
    if bvid is None:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail="Invalid Bilibili URL"
        )

    return await bilibili_embed(request, bvid)


@app.get("/{bvid}")
@app.get("/video/{bvid}")
async def embed_bilibili_video(request: fastapi.Request, bvid: str) -> fastapi.responses.Response:
    if "Discordbot" not in request.headers.get("User-Agent", ""):
        return fastapi.responses.RedirectResponse(f"https://www.bilibili.com/video/{bvid}")

    return await bilibili_embed(request, bvid)
