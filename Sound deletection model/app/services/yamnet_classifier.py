import math
from pathlib import Path

from app.config import Settings
from app.models.schemas import InstrumentWindow
from app.services.audio_processing import iter_chunks
from app.services.hosted_classifier import HostedClassifier, ProviderError
from app.services.instrument_classifier import AnalysisProgress, ProviderResult
from app.services.labels import filter_instruments


# Only used to explain empty results, never to infer instruments.
MUSIC_CONTEXT_LABELS = frozenset({
    "Music", "Song", "Background music", "Musical instrument", "Orchestra",
    "Vocal music", "Singing", "Choir", "Humming", "Rapping", "A capella",
    "Beatboxing", "Chant", "Mantra", "Lullaby", "Music for children",
    "Jingle (music)", "Soundtrack music", "Dance music", "Wedding music",
    "Happy music", "Sad music", "Tender music", "Exciting music", "Angry music",
    "Scary music", "Pop music", "Hip hop music", "Rock music", "Jazz",
    "Classical music", "Heavy metal", "Punk rock", "Grunge", "Progressive rock",
    "Rock and roll", "Psychedelic rock", "Rhythm and blues", "Soul music",
    "Reggae", "Country", "Swing music", "Bluegrass", "Funk", "Folk music",
    "Middle Eastern music", "Electronic music", "House music", "Techno",
    "Dubstep", "Disco", "Electronica", "Drum and bass", "Gospel music",
    "New-age music", "Ambient music", "Trance music", "Music of Latin America",
    "Salsa music", "Flamenco", "Blues", "Music of Africa", "Afrobeat",
    "Christian music", "Independent music", "Ska", "Traditional music",
})
FALLBACK_THRESHOLD = 0.15


def instrument_window(start, end, scores, threshold, fallback=False):
    instruments = filter_instruments(scores, threshold)
    effective_threshold = threshold
    fallback_used = False
    if not instruments and fallback and threshold > FALLBACK_THRESHOLD:
        effective_threshold = FALLBACK_THRESHOLD
        instruments = filter_instruments(scores, effective_threshold)
        fallback_used = True

    message = None
    if not instruments:
        percent = f"{effective_threshold * 100:g}%"
        if any(p["label"] in MUSIC_CONTEXT_LABELS and p["score"] >= effective_threshold for p in scores):
            message = f"YAMNet detected music, but no specific instrument reached the {percent} threshold in its top five predictions."
        elif not any(p["score"] >= effective_threshold for p in scores):
            message = f"None of YAMNet's top five predictions passed the {percent} threshold."
        else:
            message = f"Only non-instrument labels passed the {percent} threshold; no specific instrument was detected."
    return InstrumentWindow(start=start, end=end, instruments=instruments,
        raw_predictions=scores, effective_threshold=effective_threshold,
        fallback_used=fallback_used, message=message)


class YAMNetInstrumentClassifier:
    """Retain the existing hosted adapter, efficient chunking, and partial results."""
    def __init__(self, settings: Settings, classifier: HostedClassifier):
        self.settings = settings
        self.classifier = classifier

    async def analyze(self, audio: Path, duration: float, threshold: float, *, fallback: bool = False):
        count = math.ceil(round(duration * 16000) / round(self.settings.chunk_duration * 16000))
        windows = []
        fatal_error = None
        yield AnalysisProgress("classifying", total=count)
        for index, (start, end, wav) in enumerate(iter_chunks(audio, self.settings.chunk_duration)):
            try:
                if fatal_error:
                    raise fatal_error
                scores = await self.classifier.classify(wav)
                window = instrument_window(start, end, scores, threshold, fallback)
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
