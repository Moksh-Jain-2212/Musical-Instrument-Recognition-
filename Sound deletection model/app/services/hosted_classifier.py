"""Adapter for the verified Gradio 3.2 YAMNet Space. No local model imports."""
import asyncio
import base64
import math
import re
import uuid

import httpx

from app.config import SPACE_URL, Settings
from app.services.labels import MODEL_LABELS


class ProviderError(Exception):
    def __init__(self, message: str, *, fatal=False, retryable=False):
        super().__init__(message)
        self.fatal = fatal
        self.retryable = retryable


def parse_prediction(payload) -> list[dict]:
    try:
        text = payload["data"][0]
        classes, scores = text.split("classes:", 1)[1].split("scores:", 1)
        labels = re.findall(r"\[([^\[\]]+)\]", classes)
        values = re.findall(r"\[([^\[\]]+)\]", scores)
        if len(labels) != 5 or len(values) != 5 or len(set(labels)) != 5:
            raise ValueError("Expected five distinct labels")
        result = []
        for label, value in zip(labels, values):
            score = float(value)
            if label not in MODEL_LABELS or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Invalid label or score")
            result.append({"label": label, "score": score})
        return result
    except (KeyError, IndexError, TypeError, AttributeError, ValueError) as exc:
        raise ProviderError("The hosted API returned an invalid response or changed its format.", retryable=True) from exc


class HostedClassifier:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    async def classify(self, wav: bytes) -> list[dict]:
        token = self.settings.hf_token.get_secret_value().strip()
        if not token:
            raise ProviderError("Set HF_TOKEN in .env and restart the server.", fatal=True)
        payload = {"data": [{"name": "chunk.wav", "data": "data:audio/wav;base64," + base64.b64encode(wav).decode()}],
                   "fn_index": 0, "session_hash": uuid.uuid4().hex}
        for attempt in range(self.settings.api_retries + 1):
            retry_after = 2 ** attempt
            try:
                response = await self.client.post(
                    SPACE_URL + "/api/predict", json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=self.settings.api_timeout_seconds)
                if response.status_code in (401, 403):
                    raise ProviderError("Hugging Face rejected the token. Check HF_TOKEN and its access permissions.", fatal=True)
                if response.status_code == 429:
                    try:
                        retry_after = min(30, max(1, float(response.headers.get("retry-after", retry_after))))
                    except ValueError:
                        pass
                    raise ProviderError("Hosted API rate limit reached. Try again later.", retryable=True)
                if response.status_code in (408, 500, 502, 503, 504):
                    raise ProviderError("Hosted model is unavailable, busy, or waking up.", retryable=True)
                if response.status_code >= 400:
                    raise ProviderError(f"Hosted API rejected the request (HTTP {response.status_code}).", fatal=True)
                try:
                    return parse_prediction(response.json())
                except ValueError as exc:
                    raise ProviderError("Hosted API returned invalid JSON.", retryable=True) from exc
            except httpx.TimeoutException:
                error = ProviderError("Hosted API request timed out.", retryable=True)
            except httpx.RequestError:
                error = ProviderError("Cannot connect to the hosted API.", retryable=True)
            except ProviderError as exc:
                error = exc
            if error.fatal or not error.retryable or attempt == self.settings.api_retries:
                raise error
            await asyncio.sleep(retry_after)
        raise RuntimeError("Unreachable")
