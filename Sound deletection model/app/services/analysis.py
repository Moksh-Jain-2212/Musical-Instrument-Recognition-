import asyncio
import math
import tempfile
from pathlib import Path

from fastapi import UploadFile

from app.config import MODEL_NAME, SPACE_ID, Settings
from app.models.schemas import AnalysisResult, Window
from app.services.audio_processing import AudioError, decode_audio, iter_chunks
from app.services.hosted_classifier import HostedClassifier, ProviderError
from app.services.labels import filter_events
from app.services.timeline_processor import instrument_segments, merge_timeline


class UploadTooLarge(AudioError):
    pass


async def analyze_upload(file: UploadFile, settings: Settings, classifier: HostedClassifier, threshold: float):
    """Yield real progress followed by the result. All local files are temporary."""
    try:
        with tempfile.TemporaryDirectory(prefix="sound-atlas-") as folder:
            source = Path(folder) / "upload.audio"
            decoded = Path(folder) / "decoded.wav"
            total_bytes = 0
            with source.open("wb") as output:
                while data := await file.read(1024 * 1024):
                    total_bytes += len(data)
                    if total_bytes > settings.max_upload_mb * 1024 * 1024:
                        raise UploadTooLarge(f"File exceeds the {settings.max_upload_mb} MB limit.")
                    output.write(data)
            if not total_bytes:
                raise AudioError("The uploaded file is empty.")
            yield {"type": "progress", "stage": "decoding", "completed": 0, "total": None}
            duration = await asyncio.to_thread(decode_audio, source, decoded, settings)
            count = math.ceil(round(duration * 16000) / round(settings.chunk_duration * 16000))
            windows = []
            fatal_error = None
            yield {"type": "progress", "stage": "classifying", "completed": 0, "total": count}
            for index, (start, end, wav) in enumerate(iter_chunks(decoded, settings.chunk_duration)):
                try:
                    if fatal_error:
                        raise fatal_error
                    scores = await classifier.classify(wav)
                    window = Window(start=start, end=end, events=filter_events(scores, threshold))
                except ProviderError as exc:
                    if exc.fatal:
                        fatal_error = exc
                    window = Window(start=start, end=end, status="failed", error=str(exc))
                windows.append(window)
                yield {"type": "progress", "stage": "classifying", "completed": index + 1, "total": count}
            failed = sum(w.status == "failed" for w in windows)
            warnings = [
                "Community-hosted YAMNet returns only its top five AudioSet labels per chunk; other sounds may be omitted.",
                "Timestamps have chunk-level resolution. Scores are model estimates, not calibrated guarantees.",
            ]
            if failed:
                warnings.append(f"{failed} of {len(windows)} chunks could not be analyzed; failed intervals are marked explicitly.")
            if not any(w.events for w in windows if w.status == "ok"):
                warnings.append("No supported sounds exceeded the threshold in successfully analyzed chunks.")
            result = AnalysisResult(duration=duration, timeline=merge_timeline(windows), windows=windows,
                                    instruments=instrument_segments(windows), model=MODEL_NAME,
                                    provider=f"Hugging Face Space: {SPACE_ID}", chunk_duration=settings.chunk_duration,
                                    threshold=threshold, failed_chunks=failed, warnings=warnings)
            yield {"type": "result", "result": result.model_dump()}
    finally:
        await file.close()
