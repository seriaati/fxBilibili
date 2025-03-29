from contextlib import asynccontextmanager
import logging
import os
import re
from typing import AsyncGenerator

from dotenv import load_dotenv
import fastapi
from aiohttp_client_cache.session import CachedSession
from aiohttp_client_cache.backends.sqlite import SQLiteBackend
import uvicorn
from aiohttp_socks import ProxyConnector

load_dotenv()

HEADERS = {"User-Agent": "Mozilla/5.0"}
ERROR_HTML = """<!DOCTYPE html>
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
</html>"""


def extract_bilibili_video_id(url: str) -> str | None:
    match = re.search(r"https://(?:www.|m.)?bilibili.com/video/([\w]+)", url)
    return match.group(1) if match else None


@asynccontextmanager
async def app_lifespan(app: fastapi.FastAPI) -> AsyncGenerator[None, None]:
    cache = SQLiteBackend(cache_name="cache.db", expire_after=3600)
    proxy_url = os.getenv("PROXY_URL")

    app.state.session = CachedSession(
        cache=cache,
        connector=ProxyConnector.from_url(proxy_url) if proxy_url else None,
    )
    try:
        yield
    finally:
        await app.state.session.close()


logger = logging.getLogger("uvicorn")
app = fastapi.FastAPI(lifespan=app_lifespan)


@app.exception_handler(fastapi.HTTPException)
async def http_exception_handler(
    _: fastapi.Request, exc: fastapi.HTTPException
) -> fastapi.responses.HTMLResponse:
    logger.exception(f"HTTP error: {exc.status_code} - {exc.detail}")
    return fastapi.responses.HTMLResponse(
        ERROR_HTML.format(message=exc.detail), status_code=exc.status_code
    )


@app.exception_handler(Exception)
async def exception_handler(
    _: fastapi.Request, exc: Exception
) -> fastapi.responses.HTMLResponse:
    logger.exception(f"Unhandled exception: {exc}")
    return fastapi.responses.HTMLResponse(
        ERROR_HTML.format(message=str(exc)), status_code=500
    )


@app.get("/")
async def index() -> fastapi.responses.HTMLResponse:
    return fastapi.responses.HTMLResponse(
        "Usage: Append the Bilibili video ID to the URL.\n"
        "For example: /BV1xK4y1p7 or /video/BV1xK4y1p7",
    )


@app.get("/favicon.ico")
async def favicon() -> fastapi.responses.Response:
    return fastapi.responses.Response(status_code=204)


async def bilibili_embed(
    request: fastapi.Request, bvid: str
) -> fastapi.responses.Response:
    current_url = str(request.url)

    session: CachedSession = app.state.session
    async with session.get(
        f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
        headers=HEADERS,
    ) as resp:
        resp.raise_for_status()
        view_data = await resp.json()

        if view_data.get("code") != 0:
            error_msg = view_data.get("message", "Invalid Bilibili video ID")
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail=error_msg,
            )

    video_data = view_data.get("data", {})
    title = video_data.get("title", "Bilibili Video")
    description = video_data.get("desc", "")
    pic = video_data.get("pic", "")
    owner = video_data.get("owner", {})
    owner_name = owner.get("name", "Bilibili")
    stat = video_data.get("stat", {})
    view_count = stat.get("view", "0")

    async with session.get(
        f"https://api.injahow.cn/bparse/?bv={bvid}&q=64&otype=json",
    ) as resp:
        resp.raise_for_status()

        data = await resp.json()
        if data.get("code") != 0:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_404_NOT_FOUND,
                detail="Failed to retrieve video URL",
            )

        video_url = data.get("url", "")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="theme-color" content="#0fa6d8">
  <meta property="og:title" content="{owner_name} - {title}">
  <meta property="og:type" content="video">
  <meta property="og:site_name" content="Bilibili | 👁️ {view_count}">
  <meta property="og:url" content="{current_url}">
  <meta property="og:video" content="{video_url}">
  <meta property="og:video:secure_url" content="{video_url}">
  <meta property="og:video:type" content="video/mp4">
  <meta property="og:image" content="{pic}">
  <meta name="twitter:card" content="player">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{pic}">
  <meta name="twitter:player" content="{current_url}">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      background: #000;
      display: flex;
      justify-content: center;
      align-items: center;
      height: 100vh;
    }}
    video {{
      max-width: 100%;
      max-height: 100%;
    }}
  </style>
</head>
</html>"""
    return fastapi.responses.HTMLResponse(html)


@app.get("/b23/{id}")
async def bilibili_redirect(
    request: fastapi.Request, id: str
) -> fastapi.responses.RedirectResponse:
    url = f"https://b23.tv/{id}"

    if "Discordbot" not in request.headers.get("User-Agent", ""):
        return fastapi.responses.RedirectResponse(url)

    session: CachedSession = app.state.session
    async with session.get(url) as resp:
        final_url = str(resp.url)

    bvid = extract_bilibili_video_id(final_url)
    if bvid is None:
        logger.warning("Failed to extract Bilibili video ID from %s", final_url)
        return fastapi.responses.RedirectResponse(url)

    return await bilibili_embed(request, bvid)


@app.get("/{bvid}")
@app.get("/video/{bvid}")
async def bilibili_direct(
    request: fastapi.Request, bvid: str
) -> fastapi.responses.Response:
    # if "Discordbot" not in request.headers.get("User-Agent", ""):
    #     return fastapi.responses.RedirectResponse(
    #         f"https://www.bilibili.com/video/{bvid}",
    #     )

    return await bilibili_embed(request, bvid)


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=9823)
