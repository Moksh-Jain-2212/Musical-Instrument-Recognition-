import math
from pathlib import Path

from app.config import Settings
from app.models.schemas import InstrumentWindow
from app.services.audio_processing import iter_chunks
from app.services.hosted_classifier import HostedClassifier, ProviderError
from app.services.instrument_classifier import AnalysisProgress, ProviderResult
from app.services.labels import filter_instruments


class YAMNetInstrumentClassifier:
    """Retain the existing hosted adapter, efficient chunking, and partial results."""
    def __init__(self, settings: Settings, classifier: HostedClassifier):
        self.settings = settings
        self.classifier = classifier

    async def analyze(self, audio: Path, duration: float, threshold: float):
        count = math.ceil(round(duration * 16000) / round(self.settings.chunk_duration * 16000))
        windows = []
        fatal_error = None
        yield AnalysisProgress("classifying", total=count)
        for index, (start, end, wav) in enumerate(iter_chunks(audio, self.settings.chunk_duration)):
            try:
                if fatal_error:
                    raise fatal_error
                scores = await self.classifier.classify(wav)
                window = InstrumentWindow(start=start, end=end, instruments=filter_instruments(scores, threshold))
            except ProviderError as exc:
                if exc.fatal:
                    fatal_error = exc
                window = InstrumentWindow(start=start, end=end, status="failed", error=str(exc))
            windows.append(window)
            yield AnalysisProgress("classifying", completed=index + 1, total=count)
        yield ProviderResult(windows, [
            "The hosted YAMNet API exposes only its top five predictions per chunk. Broad non-instrument labels can displace instruments before filtering.",
            "Timestamps have chunk-level resolution. Scores are model estimates, not guaranteed probabilities of correctness.",
        ])
