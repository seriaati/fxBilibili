# fxBilibili

Fix Bilibili link preview embeds on Discord.

Orginal script made by [RoyRiv3r](https://github.com/RoyRiv3r).

This is made for [Embed Fixer](https://ef.seria.moe).

## Usage

- https://fxbilibili.seria.moe/b23/Mxq2mlf
- https://fxbilibili.seria.moe/BV1LZoNYZEe6
- https://fxbilibili.seria.moe/video/BV1LZoNYZEe6

## Configuration

Environment variables:

- `PROXY_URL` — optional SOCKS/HTTP proxy for outbound calls.
- `REDIS_URL` — optional Redis backend for response caching (defaults to SQLite).
- `BILIBILI_SESSDATA` — optional Bilibili `SESSDATA` cookie. Anonymous
  `playurl` calls are downgraded to 360P; supplying a logged-in cookie
  unlocks higher quality (720P / 1080P depending on account level).
- `BILIBILI_BILI_JCT`, `BILIBILI_BUVID3` — optional companion cookies.

The video URL is fetched directly from Bilibili's `playurl` endpoint
(WBI-signed for regular videos, `pgc/player/web/playurl` for bangumi).
No third-party parsing service is used.
