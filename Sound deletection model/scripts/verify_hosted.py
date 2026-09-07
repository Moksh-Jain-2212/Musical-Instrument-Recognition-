"""Verify the live Space using synthetic silence; never upload user audio here."""
import argparse
import asyncio
import base64
import io
import json
import wave

import httpx

from app.config import SPACE_ID, SPACE_URL, Settings
from app.services.hosted_classifier import HostedClassifier, parse_prediction


async def verify(public_probe: bool):
    settings = Settings()
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 80000)
    async with httpx.AsyncClient(timeout=45, follow_redirects=False) as client:
        metadata = await client.get(f"https://huggingface.co/api/spaces/{SPACE_ID}")
        metadata.raise_for_status()
        configuration = await client.get(SPACE_URL + "/config")
        configuration.raise_for_status()
        if public_probe:
            response = await client.post(SPACE_URL + "/api/predict", json={
                "session_hash": "sound-atlas-synthetic-probe", "fn_index": 0,
                "data": [{"name": "silence.wav", "data": "data:audio/wav;base64," + base64.b64encode(buffer.getvalue()).decode()}],
            })
            response.raise_for_status()
            predictions = parse_prediction(response.json())
        else:
            predictions = await HostedClassifier(settings, client).classify(buffer.getvalue())
    print(json.dumps({"space": SPACE_ID, "runtime": metadata.json().get("runtime", {}).get("stage"),
                      "gradio_version": configuration.json().get("version", "").strip(),
                      "authenticated": not public_probe, "synthetic_input": "5 seconds of silence, mono PCM16, 16 kHz",
                      "predictions": predictions}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-probe", action="store_true", help="Test public access without a token, using generated silence only.")
    arguments = parser.parse_args()
    try:
        asyncio.run(verify(arguments.public_probe))
    except Exception as exc:
        # Do not print HTTP request objects or authorization headers.
        raise SystemExit(f"Hosted verification failed ({type(exc).__name__}). Check connectivity, HF_TOKEN, and the Space status.") from None
