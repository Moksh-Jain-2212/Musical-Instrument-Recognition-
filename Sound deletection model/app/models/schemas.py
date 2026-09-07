from typing import Literal

from pydantic import BaseModel, Field


class InstrumentPrediction(BaseModel):
    name: str
    confidence: float = Field(ge=0, le=1)


class RawPrediction(BaseModel):
    label: str
    score: float = Field(ge=0, le=1, allow_inf_nan=False)


class InstrumentWindow(BaseModel):
    start: float
    end: float
    instruments: list[InstrumentPrediction] = Field(default_factory=list)
    raw_predictions: list[RawPrediction] = Field(default_factory=list)
    effective_threshold: float | None = None
    fallback_used: bool = False
    message: str | None = None
    status: Literal["ok", "failed"] = "ok"
    error: str | None = None


class TimelineEntry(BaseModel):
    start: float
    end: float
    instruments: list[InstrumentPrediction]
    status: Literal["ok", "failed"]
    effective_threshold: float | None = None
    fallback_used: bool = False
    message: str | None = None


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
    threshold: float = Field(ge=0.05, le=0.80)
    fallback_enabled: bool = False
    failed_chunks: int
    warnings: list[str]
