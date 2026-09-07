import io
import threading
from pathlib import Path

import anyio
import pytest
from starlette.datastructures import UploadFile

from app.services.analysis import UploadTooLarge, analyze_upload
from app.services.yamnet_classifier import YAMNetInstrumentClassifier
from tests.conftest import wav_bytes
from tests.test_api import Classifier


async def test_early_generator_close_cleans_upload(settings, monkeypatch):
    import app.services.analysis as analysis
    original = analysis.tempfile.TemporaryDirectory
    folders = []
    def directory(*args, **kwargs):
        value = original(*args, **kwargs)
        folders.append(Path(value.name))
        return value
    monkeypatch.setattr(analysis.tempfile, "TemporaryDirectory", directory)
    file = UploadFile(io.BytesIO(wav_bytes(6)), filename="audio.wav")
    events = analyze_upload(file, settings, Classifier(), .3)
    assert (await anext(events))["stage"] == "decoding"
    assert folders[0].exists()
    await events.aclose()
    assert not folders[0].exists()
    assert file.file.closed


async def test_cancellation_during_decode_waits_for_worker(settings, monkeypatch):
    import app.services.analysis as analysis

    started, release = threading.Event(), threading.Event()
    paths, files_survived = [], []

    def decode(source, output, settings):
        paths.extend([source, output])
        started.set()
        assert release.wait(5), "Test did not release decoder"
        files_survived.append(source.exists() and output.parent.exists())
        output.write_bytes(wav_bytes())
        return 1.0

    monkeypatch.setattr(analysis, "decode_audio", decode)
    classifier = Classifier()
    file = UploadFile(io.BytesIO(wav_bytes()), filename="audio.wav")
    updates = analyze_upload(file, settings, YAMNetInstrumentClassifier(settings, classifier), .3)
    assert (await anext(updates))["stage"] == "decoding"

    async def continue_analysis():
        async for _ in updates:
            pass

    try:
        with anyio.fail_after(5):
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(continue_analysis)
                while not started.is_set():
                    await anyio.sleep(.001)
                tasks.cancel_scope.cancel()
                # Give cancellation time to unwind before the decoder finishes.
                with anyio.CancelScope(shield=True):
                    await anyio.sleep(.02)
                    assert paths[0].exists()
                    release.set()
    finally:
        release.set()
        await updates.aclose()

    assert files_survived == [True]
    assert file.file.closed and all(not path.exists() for path in paths)
    assert not paths[0].parent.exists()
    assert classifier.calls == 0


async def test_streamed_upload_size_limit_even_without_content_length(settings):
    settings.max_upload_mb = 1
    file = UploadFile(io.BytesIO(b"x" * 1100000), filename="audio.wav")
    events = analyze_upload(file, settings, Classifier(), .3)
    with pytest.raises(UploadTooLarge):
        await anext(events)
    assert file.file.closed
