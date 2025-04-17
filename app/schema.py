from __future__ import annotations

from pydantic import BaseModel, Field


class VideoOwner(BaseModel):
    name: str = "???"


class VideoStatistics(BaseModel):
    views: int = Field(0, alias="view")


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
