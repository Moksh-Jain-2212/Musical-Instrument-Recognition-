import io
import subprocess
import wave

import pytest

from app.services.audio_processing import AudioError, decode_audio, ffmpeg_executable, iter_chunks
from tests.conftest import wav_bytes


def test_stereo_resampling_and_chunk_timestamps(tmp_path, settings):
    source, decoded = tmp_path / "input.wav", tmp_path / "decoded.wav"
    source.write_bytes(wav_bytes(duration=11.25, rate=44100, channels=2))
    duration = decode_audio(source, decoded, settings)
    assert duration == pytest.approx(11.25, abs=.001)
    chunks = list(iter_chunks(decoded, 5))
    assert [(s, e) for s, e, _ in chunks] == [(0, 5), (5, 10), (10, 11.25)]
    with wave.open(io.BytesIO(chunks[0][2])) as audio:
        assert audio.getframerate() == 16000
        assert audio.getnchannels() == 1
        assert audio.getsampwidth() == 2
        assert audio.getnframes() == 80000


@pytest.mark.parametrize("extension,codec", [("mp3", "libmp3lame"), ("m4a", "aac"), ("webm", "libopus")])
def test_compressed_formats(tmp_path, settings, extension, codec):
    source = tmp_path / "source.wav"
    source.write_bytes(wav_bytes(1))
    compressed = tmp_path / f"input.{extension}"
    subprocess.run([ffmpeg_executable(settings), "-y", "-loglevel", "error", "-i", str(source), "-c:a", codec, str(compressed)], check=True)
    assert decode_audio(compressed, tmp_path / "decoded.wav", settings) == pytest.approx(1, abs=.1)


@pytest.mark.parametrize("data", [b"", b"not audio at all", wav_bytes(0)])
def test_empty_invalid_audio(tmp_path, settings, data):
    source = tmp_path / "input.wav"
    source.write_bytes(data)
    with pytest.raises(AudioError):
        decode_audio(source, tmp_path / "output.wav", settings)


def test_duration_limit(tmp_path, settings):
    settings.max_duration_seconds = 1
    source = tmp_path / "input.wav"
    source.write_bytes(wav_bytes(2))
    with pytest.raises(AudioError, match="limit"):
        decode_audio(source, tmp_path / "output.wav", settings)


def test_missing_ffmpeg(settings):
    settings.ffmpeg_path = "/missing/ffmpeg"
    with pytest.raises(AudioError, match="FFMPEG_PATH"):
        ffmpeg_executable(settings)


def test_exact_chunk_boundary(tmp_path):
    path = tmp_path / "input.wav"
    path.write_bytes(wav_bytes(10))
    assert [(s, e) for s, e, _ in iter_chunks(path, 5)] == [(0, 5), (5, 10)]
