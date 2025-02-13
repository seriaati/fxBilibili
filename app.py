from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

import fastapi
from aiohttp_client_cache.session import CachedSession
from aiohttp_client_cache.backends.sqlite import SQLiteBackend
import uvicorn


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
  <meta property="og:url" content="{current_url}">
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


@asynccontextmanager
async def app_lifespan(app: fastapi.FastAPI) -> AsyncGenerator[None, None]:
    app.state.session = CachedSession(
        cache=SQLiteBackend(cache_name="cache.db", expire_after=3600),
    )
    try:
        yield
    finally:
        await app.state.session.close()


logger = logging.getLogger("uvicorn")
app = fastapi.FastAPI(lifespan=app_lifespan)


def error_response(
    message: str, current_url: str = ""
) -> fastapi.responses.HTMLResponse:
    return fastapi.responses.HTMLResponse(
        ERROR_HTML.format(message=message, current_url=current_url),
    )


@app.get("/")
async def index() -> fastapi.responses.HTMLResponse:
    return fastapi.responses.HTMLResponse(
        "Usage: Append the Bilibili video ID to the URL.\n"
        "For example: /BV1xK4y1p7 or /video/BV1xK4y1p7",
    )


@app.get("/favicon.ico")
async def favicon() -> fastapi.responses.Response:
    return fastapi.responses.Response(status=204)


@app.get("/{bvid}")
@app.get("/video/{bvid}")
async def bilibili_embed(
    request: fastapi.Request, bvid: str
) -> fastapi.responses.Response:
    if "Discordbot" not in request.headers.get("User-Agent", ""):
        return fastapi.responses.RedirectResponse(
            f"https://www.bilibili.com/video/{bvid}",
        )

    current_url = str(request.url)

    session: CachedSession = app.state.session
    async with session.get(
        f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
        headers=HEADERS,
    ) as resp:
        if resp.status != 200:
            return error_response("Error fetching video data", current_url)

        try:
            view_data = await resp.json()
        except Exception:
            return error_response("Error decoding video data", current_url)

        if view_data.get("code") != 0:
            error_msg = view_data.get("message", "Invalid Bilibili video ID")
            return error_response(error_msg, current_url)

    video_data = view_data.get("data", {})
    title = video_data.get("title", "Bilibili Video")
    description = video_data.get("desc", "")
    pic = video_data.get("pic", "")
    owner = video_data.get("owner", {})
    owner_name = owner.get("name", "Bilibili")
    stat = video_data.get("stat", {})
    view_count = stat.get("view", "0")

    dimension = video_data.get("dimension", {})
    width = dimension.get("width", 1920)
    height = dimension.get("height", 1080)

    async with session.get(
        f"https://api.injahow.cn/bparse/?bv={bvid}&q=64&otype=json",
    ) as resp:
        if resp.status != 200:
            return error_response("Error fetching video data", current_url)

        try:
            data = await resp.json()
        except Exception:
            return error_response("Error decoding video data", current_url)

        if data.get("code") != 0:
            error_msg = data.get("message", "Invalid Bilibili video ID")
            return error_response(error_msg, current_url)

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
  <meta property="og:video:width" content={width}>
  <meta property="og:video:height" content={height}>
  <meta property="og:image" content="{pic}">
  <meta name="twitter:card" content="player">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{pic}">
  <meta name="twitter:player" content="{current_url}">
  <meta name="twitter:player:width" content={width}>
  <meta name="twitter:player:height" content={height}>
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


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=9823)
