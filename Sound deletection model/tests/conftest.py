import io
import math
import struct
import wave

import pytest

from app.config import Settings


def wav_bytes(duration=1, rate=16000, channels=1, silent=False):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(rate)
        samples = [0 if silent else int(6000 * math.sin(2 * math.pi * 440 * i / rate)) for i in range(round(duration * rate))]
        output.writeframes(b"".join(struct.pack("<h", sample) * channels for sample in samples))
    return buffer.getvalue()


@pytest.fixture
def settings():
    return Settings(_env_file=None, hf_token="hf_test_not_a_real_token", api_retries=0)


@pytest.fixture
def valid_response():
    return {"data": ["The main sound is: [Music], classes: [Music], [Piano], [Drum], [Singing], [Speech], scores: [0.95], [0.91], [0.73], [0.62], [0.10]"]}
