"""Common provider contract; both providers feed the same timeline processor."""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.models.schemas import InstrumentWindow


@dataclass
class AnalysisProgress:
    stage: str
    completed: int = 0
    total: int | None = None

    def message(self):
        return {"type": "progress", "stage": self.stage, "completed": self.completed, "total": self.total}


@dataclass
class ProviderResult:
    windows: list[InstrumentWindow]
    warnings: list[str]


class InstrumentClassifier(Protocol):
    def analyze(self, audio: Path, duration: float, threshold: float, *, fallback: bool = False) -> AsyncIterator[AnalysisProgress | ProviderResult]: ...
