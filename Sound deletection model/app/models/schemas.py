from typing import Literal

from pydantic import BaseModel, Field


class Event(BaseModel):
    name: str
    confidence: float = Field(ge=0, le=1)


class Window(BaseModel):
    start: float
    end: float
    events: list[Event] = Field(default_factory=list)
    status: Literal["ok", "failed"] = "ok"
    error: str | None = None


class TimelineEntry(BaseModel):
    start: float
    end: float
    events: list[str]
    confidences: dict[str, float]
    status: Literal["ok", "failed"]


class Segment(BaseModel):
    start: float
    end: float
    average_confidence: float


class AnalysisResult(BaseModel):
    duration: float
    timeline: list[TimelineEntry]
    windows: list[Window]
    instruments: dict[str, list[Segment]]
    model: str
    provider: str
    chunk_duration: float
    threshold: float
    failed_chunks: int
    warnings: list[str]
