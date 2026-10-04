"""Discord component embed (Components V2 link preview) for a Bilibili video."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:
    from app.schema import VideoData

MAX_BYTES = 3000
MIN_DESC = 150
ACCENT = 0xFB7299  # Bilibili pink
VIDEO_URL = "https://www.bilibili.com/video/{bvid}"
SPACE_URL = "https://space.bilibili.com/{mid}"
SEARCH_URL = "https://search.bilibili.com/all?keyword={kw}"

_MD = re.compile(r"([\\*_~`|\[\]<>])")
_LEAD = re.compile(r"^(\s*)([#>\-+]|\d+\.)", re.MULTILINE)
_TAG = re.compile(r"#([^#\s]{1,32})#")  # Bilibili hashtags are closed: #tag#
# Discord renders a masked link as raw markdown when its text contains emoji.
_EMOJI = re.compile(r"[\U0001F000-\U0001FAFF\u2300-\u23FF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]")


def _esc(text: str) -> str:
    text = _MD.sub(r"\\\1", text)
    return _LEAD.sub(lambda m: m.group(1) + "\\" + m.group(2), text)


def _link(text: str, url: str) -> str:
    return text if _EMOJI.search(text) else f"[{text}]({url})"


def _cut(text: str, n: int) -> str:
    return text if len(text) <= n else text[: max(n - 1, 0)].rstrip() + "…"


def _line(line: str) -> str:
    parts = _TAG.split(line)  # text, tag, text, tag, ...
    out: list[str] = []
    for i, part in enumerate(parts):
        if i % 2:
            out.append(_link(f"#{_esc(part)}#", SEARCH_URL.format(kw=quote(part))))
        else:
            out.append(_esc(part) if i == 0 else _MD.sub(r"\\\1", part))
    return "".join(out)


def _caption(desc: str, n: int) -> str:
    return "\n".join(_line(line) for line in _cut(desc, n).split("\n"))


def _build(
    video: VideoData, video_url: str, avatar_url: str | None, *, desc_len: int, staff_max: int
) -> dict[str, Any]:
    bvid, owner = video.bvid, video.owner
    owner_link = (
        _link(_esc(owner.name), SPACE_URL.format(mid=owner.mid)) if owner.mid else _esc(owner.name)
    )

    header = f"### {owner_link}"
    staff = [s for s in video.staff or [] if s.mid != owner.mid]
    if staff:
        names = " · ".join(
            _link(_esc(s.name), SPACE_URL.format(mid=s.mid)) for s in staff[:staff_max]
        )
        more = f" +{len(staff) - staff_max}" if len(staff) > staff_max else ""
        header += f"\n-# 👥 with {names}{more}"

    body = f"**{_link(_esc(video.title), VIDEO_URL.format(bvid=bvid))}**"
    if video.description and video.description != "-":
        body += "\n" + _caption(video.description, desc_len)

    texts = [{"type": 10, "content": header}, {"type": 10, "content": body}]
    components: list[dict[str, Any]] = [
        {"type": 9, "components": texts, "accessory": {"type": 11, "media": {"url": avatar_url}}}
        if avatar_url
        else {"type": 10, "content": f"{header}\n{body}"},
        {"type": 14, "divider": False, "spacing": 2},
        {"type": 12, "items": [{"media": {"url": video_url}}]},
    ]

    info: list[str] = []
    if video.videos > 1 and video.pages:
        info.append(f"📑 Part 1 of {video.videos} · {_esc(video.pages[0].part)}")
    if video.ugc_season:
        info.append(f"📚 {_esc(video.ugc_season.title)} · {video.ugc_season.ep_count:,} videos")
    if video.honor_reply and video.honor_reply.honor:
        info.append("🏆 " + " · ".join(_esc(h.desc) for h in video.honor_reply.honor))
    if video.argue_info and video.argue_info.argue_msg:
        info.append(f"⚠️ {_esc(video.argue_info.argue_msg)}")
    if info:
        components.append({"type": 10, "content": "\n".join(f"-# {line}" for line in info)})

    stats = video.stats
    footer = (
        f"👁️ **{stats.views:,}** · 👍 **{stats.likes:,}** · "
        f"🪙 **{stats.coins:,}** · ⭐ **{stats.favorites:,}**"
    )
    if video.pubdate:
        footer += f"\n<t:{video.pubdate}:f>"

    buttons = [
        {"type": 2, "style": 5, "label": "Watch on Bilibili", "url": VIDEO_URL.format(bvid=bvid)}
    ]
    if owner.mid:
        buttons.append(
            {
                "type": 2,
                "style": 5,
                "label": _cut(owner.name, 80),
                "url": SPACE_URL.format(mid=owner.mid),
            }
        )

    components += [
        {"type": 14, "divider": True, "spacing": 2},
        {"type": 10, "content": footer},
        {"type": 14, "divider": False, "spacing": 1},
        {"type": 1, "components": buttons},
    ]
    return {"component": {"type": 17, "accent_color": ACCENT, "components": components}}


def _serialize(payload: dict[str, Any]) -> str:
    # Escape "<" so the JSON cannot close the surrounding <script> tag.
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def get_component_embed(video: VideoData, *, video_url: str, avatar_url: str | None) -> str | None:
    """Return the serialized payload, or None when it cannot fit Discord's byte cap.

    The description gets whatever bytes remain; if the collaborator list leaves it
    fewer than MIN_DESC chars, retry with fewer collaborators.
    """
    want = min(len(video.description), MIN_DESC)
    fallback: str | None = None
    for staff_max in (5, 3, 1, 0):
        lo, hi = 0, len(video.description)
        best: str | None = None
        while lo <= hi:
            mid = (lo + hi) // 2
            serialized = _serialize(
                _build(video, video_url, avatar_url, desc_len=mid, staff_max=staff_max)
            )
            if len(serialized.encode()) <= MAX_BYTES:
                best, lo = serialized, mid + 1
            else:
                hi = mid - 1
        if best is not None and hi >= want:
            return best
        fallback = fallback or best
    return fallback
