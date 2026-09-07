"""Decode once to a bounded PCM file; keep only one short chunk in memory."""
import io
import shutil
import subprocess
import wave
from pathlib import Path

from app.config import Settings

SAMPLE_RATE = 16000


class AudioError(ValueError):
    pass


def ffmpeg_executable(settings: Settings) -> str:
    if settings.ffmpeg_path:
        if not Path(settings.ffmpeg_path).is_file():
            raise AudioError("FFMPEG_PATH does not point to an FFmpeg executable.")
        return settings.ffmpeg_path
    system = shutil.which("ffmpeg")
    if system:
        return system
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError) as exc:
        raise AudioError("FFmpeg is missing. Install FFmpeg or imageio-ffmpeg.") from exc


def decode_audio(source: Path, output: Path, settings: Settings) -> float:
    # Restrict decoders to local input; playlists cannot fetch network resources.
    command = [ffmpeg_executable(settings), "-hide_banner", "-loglevel", "error",
               "-nostdin", "-y", "-protocol_whitelist", "file,pipe",
               "-i", str(source), "-map", "0:a:0", "-vn", "-ac", "1", "-ar",
               str(SAMPLE_RATE), "-t", str(settings.max_duration_seconds + 1),
               "-c:a", "pcm_s16le", str(output)]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=120)
    except FileNotFoundError as exc:
        raise AudioError("FFmpeg is missing. Install it or set FFMPEG_PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioError("Audio decoding timed out. Try a shorter file.") from exc
    except (subprocess.CalledProcessError, OSError) as exc:
        raise AudioError("Cannot decode this file. Upload a valid WAV, MP3, M4A, or WebM audio file.") from exc
    try:
        with wave.open(str(output), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
    except (wave.Error, EOFError) as exc:
        raise AudioError("The decoded audio is invalid.") from exc
    if duration <= 0:
        raise AudioError("The audio file is empty.")
    if duration > settings.max_duration_seconds:
        raise AudioError(f"Audio exceeds the {settings.max_duration_seconds // 60}-minute limit.")
    return duration


def iter_chunks(path: Path, chunk_duration: float):
    with wave.open(str(path), "rb") as source:
        rate = source.getframerate()
        total = source.getnframes()
        size = round(chunk_duration * rate)
        for start in range(0, total, size):
            frames = source.readframes(size)
            end = min(start + size, total)
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as chunk:
                chunk.setnchannels(1)
                chunk.setsampwidth(2)
                chunk.setframerate(rate)
                chunk.writeframes(frames)
            yield start / rate, end / rate, buffer.getvalue()
