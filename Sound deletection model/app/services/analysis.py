import tempfile
from contextlib import aclosing
from pathlib import Path

import anyio
from fastapi import UploadFile

from app.config import Settings
from app.models.schemas import AnalysisResult
from app.services.audio_processing import AudioError, decode_audio
from app.services.instrument_classifier import AnalysisProgress, InstrumentClassifier, ProviderResult
from app.services.timeline_processor import instrument_segments, merge_timeline


class UploadTooLarge(AudioError):
    pass


async def analyze_upload(file: UploadFile, settings: Settings, classifier: InstrumentClassifier, threshold: float, *, fallback: bool = False):
    """Yield real progress followed by the result. All local files are temporary."""
    try:
        with tempfile.TemporaryDirectory(prefix="instrument-timeline-") as folder:
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
            # Finish the worker before cancellation removes the files it is using.
            duration = await anyio.to_thread.run_sync(decode_audio, source, decoded, settings)
            await anyio.lowlevel.checkpoint()
            provider_result = None
            fallback = fallback and settings.instrument_provider == "yamnet"
            async with aclosing(classifier.analyze(decoded, duration, threshold, fallback=fallback)) as updates:
                async for update in updates:
                    if isinstance(update, AnalysisProgress):
                        yield update.message()
                    elif isinstance(update, ProviderResult):
                        provider_result = update
            if provider_result is None:
                raise RuntimeError("Instrument provider did not return a result")
            windows = provider_result.windows
            failed = sum(w.status == "failed" for w in windows)
            warnings = list(provider_result.warnings)
            if failed:
                warnings.append(f"{failed} of {len(windows)} analysis intervals failed; these intervals are marked explicitly.")
            if failed < len(windows) and not any(w.instruments for w in windows if w.status == "ok"):
                warnings.append("No specific musical instrument was confidently detected in successfully analyzed intervals.")
            if any(w.fallback_used for w in windows):
                warnings.append("Optional 15% fallback filtering was applied to empty intervals using the same raw predictions, without additional API calls. See each window's effective_threshold and fallback_used.")
            result = AnalysisResult(duration=duration, timeline=merge_timeline(windows), windows=windows,
                                    instrument_tracks=instrument_segments(windows), model=settings.model_name,
                                    provider=settings.instrument_provider,
                                    chunk_duration=settings.chunk_duration if settings.instrument_provider == "yamnet" else None,
                                    threshold=threshold, fallback_enabled=fallback, failed_chunks=failed, warnings=warnings)
            yield {"type": "result", "result": result.model_dump()}
    finally:
        with anyio.CancelScope(shield=True):
            await file.close()
