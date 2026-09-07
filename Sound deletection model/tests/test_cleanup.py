import io
from pathlib import Path

import pytest
from starlette.datastructures import UploadFile

from app.services.analysis import UploadTooLarge, analyze_upload
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


async def test_streamed_upload_size_limit_even_without_content_length(settings):
    settings.max_upload_mb = 1
    file = UploadFile(io.BytesIO(b"x" * 1100000), filename="audio.wav")
    events = analyze_upload(file, settings, Classifier(), .3)
    with pytest.raises(UploadTooLarge):
        await anext(events)
    assert file.file.closed
