from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import urllib.parse
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aiohttp

logger = logging.getLogger("uvicorn")

# fmt: off
WBI_MIXIN_TABLE = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)
# fmt: on

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Origin": "https://www.bilibili.com",
}

WBI_NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
WBI_VIEW_URL = "https://api.bilibili.com/x/web-interface/wbi/view"
WBI_PLAYURL = "https://api.bilibili.com/x/player/wbi/playurl"
LEGACY_PLAYURL = "https://api.bilibili.com/x/player/playurl"
PGC_PLAYURL = "https://api.bilibili.com/pgc/player/web/playurl"

# Refresh WBI keys at most this often (seconds).
WBI_TTL = 3600


def build_cookies() -> dict[str, str]:
    cookies: dict[str, str] = {}
    for env, name in (
        ("BILIBILI_SESSDATA", "SESSDATA"),
        ("BILIBILI_BILI_JCT", "bili_jct"),
        ("BILIBILI_BUVID3", "buvid3"),
    ):
        v = os.getenv(env)
        if v:
            cookies[name] = v
    return cookies


class WbiSigner:
    """Caches the WBI mixin key and signs request params."""

    def __init__(self) -> None:
        self._mixin_key: str | None = None
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    async def _refresh(self, session: aiohttp.ClientSession) -> None:
        async with session.get(
            WBI_NAV_URL, headers=DEFAULT_HEADERS, cookies=build_cookies()
        ) as resp:
            resp.raise_for_status()
            data: dict[str, Any] = await resp.json()
        wbi = data["data"]["wbi_img"]
        img_key = wbi["img_url"].rsplit("/", 1)[1].split(".")[0]
        sub_key = wbi["sub_url"].rsplit("/", 1)[1].split(".")[0]
        raw = img_key + sub_key
        self._mixin_key = "".join(raw[i] for i in WBI_MIXIN_TABLE)[:32]
        self._fetched_at = time.time()
        logger.info("Refreshed WBI mixin key")

    async def sign(self, session: aiohttp.ClientSession, params: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            if self._mixin_key is None or time.time() - self._fetched_at > WBI_TTL:
                await self._refresh(session)
        assert self._mixin_key is not None

        signed: dict[str, str] = {}
        forbidden = "!'()*"
        for k, v in params.items():
            sv = str(v)
            for c in forbidden:
                sv = sv.replace(c, "")
            signed[k] = sv
        signed["wts"] = str(int(time.time()))

        query = urllib.parse.urlencode(sorted(signed.items()))
        signed["w_rid"] = hashlib.md5(  # noqa: S324  # WBI signature, not security
            (query + self._mixin_key).encode()
        ).hexdigest()
        return signed


_signer = WbiSigner()


def _extract_durl(payload: dict[str, Any]) -> str:
    durls = payload.get("durl")
    if not durls:
        msg = "Playurl response has no 'durl' (likely DASH-only — verify fnval/platform parameters)"
        raise ValueError(msg)
    return durls[0]["url"]


def _unwrap(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("code", 0) != 0:
        msg = f"Bilibili playurl error {data.get('code')}: {data.get('message') or data}"
        raise ValueError(msg)
    # x/player returns under .data, pgc under .result, sometimes nested
    # under result.video_info.
    for key in ("data", "result"):
        inner = data.get(key)
        if isinstance(inner, dict):
            if "durl" in inner or "dash" in inner:
                return inner
            video_info = inner.get("video_info")
            if isinstance(video_info, dict):
                return video_info
            return inner
    return data


def _video_params(*, bvid: str, cid: int, qn: int) -> dict[str, Any]:
    return {
        "bvid": bvid,
        "cid": cid,
        "qn": qn,  # 16=360P, 32=480P, 64=720P, 80=1080P
        "fnval": 1,
        "fnver": 0,
        "fourk": 1,
        "platform": "html5",
        "high_quality": 1,
    }


async def _request_json(
    session: aiohttp.ClientSession, url: str, params: dict[str, Any]
) -> dict[str, Any]:
    async with session.get(
        url, params=params, headers=DEFAULT_HEADERS, cookies=build_cookies()
    ) as resp:
        resp.raise_for_status()
        return await resp.json()


async def get_video_view(session: aiohttp.ClientSession, *, bvid: str) -> dict[str, Any]:
    """Return the raw `data` object of the WBI-signed video view API.

    The unsigned `x/web-interface/view` endpoint is behind risk control and
    answers 412 for non-browser clients; the `wbi/view` variant does not.
    """
    signed = await _signer.sign(session, {"bvid": bvid})
    data = await _request_json(session, WBI_VIEW_URL, signed)
    if data.get("code") != 0:
        msg = data.get("message") or "Invalid Bilibili video ID"
        raise ValueError(msg)
    return data["data"]


async def get_video_play_url(
    session: aiohttp.ClientSession, *, bvid: str, cid: int, qn: int = 80
) -> str:
    """Return an MP4 URL for a regular Bilibili video."""
    raw = _video_params(bvid=bvid, cid=cid, qn=qn)
    try:
        signed = await _signer.sign(session, raw)
        data = await _request_json(session, WBI_PLAYURL, signed)
        return _extract_durl(_unwrap(data))
    except Exception as exc:
        logger.warning("WBI playurl failed (%s); falling back to legacy", exc)
        data = await _request_json(session, LEGACY_PLAYURL, raw)
        return _extract_durl(_unwrap(data))


async def get_bangumi_play_url(
    session: aiohttp.ClientSession, *, ep_id: str, cid: int, qn: int = 80
) -> str:
    """Return an MP4 URL for a Bilibili bangumi episode."""
    params: dict[str, Any] = {
        "ep_id": ep_id,
        "cid": cid,
        "qn": qn,
        "fnval": 1,
        "fnver": 0,
        "fourk": 1,
        "platform": "html5",
        "high_quality": 1,
    }
    data = await _request_json(session, PGC_PLAYURL, params)
    return _extract_durl(_unwrap(data))
