from __future__ import annotations

from pydantic import BaseModel, Field


class VideoOwner(BaseModel):
    name: str = "???"
    mid: int | None = None
    face: str | None = None


class VideoStaff(BaseModel):
    mid: int
    name: str


class VideoSeason(BaseModel):
    title: str
    ep_count: int = 0


class VideoHonor(BaseModel):
    desc: str


class VideoHonorReply(BaseModel):
    honor: list[VideoHonor] = Field(default_factory=list)


class VideoArgueInfo(BaseModel):
    argue_msg: str = ""


class VideoStatistics(BaseModel):
    views: int = Field(0, alias="view")
    coins: int = Field(0, alias="coin")
    shares: int = Field(0, alias="share")
    likes: int = Field(0, alias="like")
    favorites: int = Field(0, alias="favorite")


class VideoDimension(BaseModel):
    width: int = 1920
    height: int = 1080


class VideoPage(BaseModel):
    cid: int
    first_frame: str | None = None
    part: str = ""


class VideoData(BaseModel):
    bvid: str
    aid: int
    cid: int
    title: str
    description: str = Field(alias="desc")
    owner: VideoOwner
    stats: VideoStatistics = Field(alias="stat")
    dimension: VideoDimension
    thumbnail: str = Field(alias="pic")

    pages: list[VideoPage] = Field(default_factory=list)

    pubdate: int | None = None
    videos: int = 1
    staff: list[VideoStaff] | None = None
    ugc_season: VideoSeason | None = None
    honor_reply: VideoHonorReply | None = None
    argue_info: VideoArgueInfo | None = None


class EpisodeInfo(BaseModel):
    ep_id: str
    bvid: str
    cid: int
    aid: int | None = None
