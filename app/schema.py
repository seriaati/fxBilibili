from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VideoOwner(BaseModel):
    name: str = "???"


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
    first_frame: str | None = None


class VideoData(BaseModel):
    title: str
    description: str = Field(alias="desc")
    owner: VideoOwner
    stats: VideoStatistics = Field(alias="stat")
    dimension: VideoDimension
    thumbnail: str = Field(alias="pic")

    pages: list[VideoPage] = Field(default_factory=list)


class VideoURLRequest(BaseModel):
    bv: str | None = None
    ep: str | None = None
    type: Literal["video", "bangumi"] = "video"
    q: Literal[16, 32, 64, 80] = 64
    p: int = 1
    otype: Literal["json", "url", "dplayer"] = "json"
