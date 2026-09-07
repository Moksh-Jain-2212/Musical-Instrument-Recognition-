from typing import Literal

from pydantic import BaseModel, Field


class InstrumentPrediction(BaseModel):
    name: str
    confidence: float = Field(ge=0, le=1)


class InstrumentWindow(BaseModel):
    start: float
    end: float
    instruments: list[InstrumentPrediction] = Field(default_factory=list)
    status: Literal["ok", "failed"] = "ok"
    error: str | None = None


class TimelineEntry(BaseModel):
    start: float
    end: float
    instruments: list[InstrumentPrediction]
    status: Literal["ok", "failed"]


class InstrumentSegment(BaseModel):
    start: float
    end: float
    average_confidence: float


class AnalysisResult(BaseModel):
    duration: float
    timeline: list[TimelineEntry]
    windows: list[InstrumentWindow]
    instrument_tracks: dict[str, list[InstrumentSegment]]
    model: str
    provider: str
    chunk_duration: float | None
    threshold: float
    failed_chunks: int
    warnings: list[str]
