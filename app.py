#!/usr/bin/env python3
import asyncio
import os
import httpx
from hypercorn.config import Config
from hypercorn.asyncio import serve
from quart import Quart, Response, request

app = Quart(__name__)
app.url_map.strict_slashes = False

HEADERS = {"User-Agent": "Mozilla/5.0"}


def error_page(message: str, current_url: str = "") -> Response:
    html = f"""<!DOCTYPE html>
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
    return Response(html, content_type="text/html")


@app.route("/")
async def index():
    return (
        "Usage: Append the Bilibili video ID to the URL. "
        "For example: /BV1xK4y1p7 or /video/BV1xK4y1p7"
    )


@app.route("/favicon.ico")
async def favicon():
    return Response(status=204)


@app.route("/<bvid>")
@app.route("/video/<bvid>")
async def bilibili_embed(bvid: str):
    current_url = str(request.url)

    async with httpx.AsyncClient() as client:
        view_res = await client.get(
            f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
            headers=HEADERS,
        )
    if view_res.status_code != 200 or not view_res.content:
        return error_page("Error fetching video data", current_url)
    try:
        view_data = view_res.json()
    except Exception:
        return error_page("Error decoding video data", current_url)
    if view_data.get("code") != 0:
        error_msg = view_data.get("message", "Invalid Bilibili video ID")
        return error_page(error_msg, current_url)
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

    pages = video_data.get("pages", [])
    if not pages:
        return error_page("No video pages found", current_url)
    cid = pages[0].get("cid")

    async with httpx.AsyncClient() as client:
        play_res = await client.get(
            f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&otype=json&platform=html5&high_quality=1",
            headers=HEADERS,
        )
    if play_res.status_code != 200 or not play_res.content:
        return error_page("Error fetching video stream", current_url)
    try:
        play_data = play_res.json()
    except Exception:
        return error_page("Error decoding video stream", current_url)
    if play_data.get("code") != 0:
        return error_page("Error in video stream data", current_url)
    durls = play_data.get("data", {}).get("durl", [])
    if not durls:
        return error_page("No video stream found", current_url)
    video_url = durls[0].get("url")
    if not video_url:
        return error_page("No valid video URL", current_url)

    user_agent = request.headers.get("User-Agent", "")
    redirect_url = f"https://www.bilibili.com/video/{bvid}"
    if "Discordbot" not in user_agent:
        redirection = (
            f'<meta http-equiv="refresh" content="0; url={redirect_url}">'
            f'<script>window.location.replace("{redirect_url}");</script>'
        )
    else:
        redirection = ""

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
  {redirection}
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
    return Response(html, content_type="text/html")


if __name__ == "__main__":
    config = Config()
    config.bind = ["localhost:9823"]
    asyncio.run(serve(app, config))
