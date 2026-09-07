import json

import httpx
import pytest

from app.services.gemini_classifier import (
    API_ORIGIN, GeminiInstrumentClassifier, normalize_segments, parse_generated_response, response_schema,
)
from app.services.hosted_classifier import ProviderError
from app.services.instrument_classifier import AnalysisProgress, ProviderResult
from app.services.timeline_processor import instrument_segments
from tests.conftest import wav_bytes


def segment(start, end, **instruments):
    return {"start": start, "end": end, "instruments": [{"name": n, "confidence": s} for n, s in instruments.items()]}


def generated(payload):
    return {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}]}


def test_overlap_gaps_and_independent_tracks():
    result = normalize_segments({"segments": [segment(2, 10, Piano=.8), segment(5, 12, Drums=.9)]}, 15, .3)
    assert [(w.start, w.end) for w in result.windows] == [(0, 2), (2, 5), (5, 10), (10, 12), (12, 15)]
    assert result.windows[0].instruments == result.windows[-1].instruments == []
    assert {i.name for i in result.windows[2].instruments} == {"Drums", "Piano"}
    tracks = instrument_segments(result.windows)
    assert (tracks["Piano"][0].start, tracks["Piano"][0].end) == (2, 10)
    assert (tracks["Drums"][0].start, tracks["Drums"][0].end) == (5, 12)


def test_filter_semantic_non_instruments_and_aliases():
    result = normalize_segments({"segments": [segment(0, 5, Music=.99, Speech=.99, Singing=.99,
        **{"Bass guitar": .8, "Drum kit": .9, "Orchestra": .99, "Piano": .2})]}, 5, .3)
    assert {i.name for i in result.windows[0].instruments} == {"Bass Guitar", "Drums"}
    assert any("removed" in w for w in result.warnings)


def test_gemini_families_and_empty_output():
    result = normalize_segments({"segments": [segment(0, 5, Strings=.8, Woodwinds=.7, Brass=.9)]}, 5, .3)
    assert {i.name for i in result.windows[0].instruments} == {"Strings", "Woodwinds", "Brass"}
    empty = normalize_segments({"segments": []}, 5, .3)
    assert len(empty.windows) == 1 and empty.windows[0].instruments == []


@pytest.mark.parametrize("payload", [{}, None, {"segments": "wrong"}, {"segments": [segment(-1, 5, Piano=.8)]},
    {"segments": [segment(5, 3, Piano=.8)]}, {"segments": [segment(0, 7, Piano=.8)]},
    {"segments": [segment(0, 5, Piano=float("nan"))]}, {"segments": [segment(0, 5, Piano=88)]},
    {"segments": [segment(0, 5, Piano="0.8")]}, {"segments": [segment(0, 5, Piano=True)]}])
def test_invalid_semantic_output(payload):
    with pytest.raises(ProviderError):
        normalize_segments(payload, 5, .3)


def test_rounding_clamps_to_duration_and_overlaps_take_max():
    result = normalize_segments({"segments": [segment(0, 5.03, Piano=.7), segment(1, 4, Piano=.9)]}, 5, .3)
    assert result.windows[-1].end == 5
    track = instrument_segments(result.windows)["Piano"][0]
    assert track.average_confidence == pytest.approx((.7 * 2 + .9 * 3) / 5)


@pytest.mark.parametrize("payload", [{}, {"candidates": []}, {"candidates": [{"finishReason": "MAX_TOKENS"}]},
    {"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": "bad json"}]}}]}])
def test_blocked_truncated_or_invalid_json(payload):
    with pytest.raises(ProviderError):
        parse_generated_response(payload)


def test_schema_contains_instruments_only():
    names = response_schema()["properties"]["segments"]["items"]["properties"]["instruments"]["items"]["properties"]["name"]["enum"]
    assert "Bass Guitar" in names and "Strings" in names
    assert not {"Music", "Speech", "Vocals", "Orchestra", "Silence"} & set(names)


@pytest.fixture
def gemini_settings(settings):
    settings.instrument_provider = "gemini"
    settings.gemini_api_key = type(settings.hf_token)("test-gemini-key")
    return settings


@pytest.fixture
def audio_file(tmp_path):
    audio = tmp_path / "complete.wav"
    audio.write_bytes(wav_bytes(6))
    return audio


class GeminiAPI:
    def __init__(self, output=None, *, generation_status=200, delete_status=200, processing=False):
        self.requests = []
        self.output = output or generated({"segments": [segment(0, 6, Piano=.88, Drums=.79)]})
        self.generation_status = generation_status
        self.delete_status = delete_status
        self.processing = processing

    def __call__(self, request):
        self.requests.append(request)
        assert request.headers["x-goog-api-key"] == "test-gemini-key"
        path = request.url.path
        if request.method == "DELETE":
            return httpx.Response(self.delete_status, json={})
        if "upload_id" in request.url.params:
            assert request.content.startswith(b"RIFF")
            return httpx.Response(200, json={"file": {"name": "files/test-audio", "uri": API_ORIGIN + "/v1beta/files/test-audio", "state": "PROCESSING" if self.processing else "ACTIVE"}})
        if path == "/upload/v1beta/files":
            return httpx.Response(200, headers={"x-goog-upload-url": API_ORIGIN + "/upload/v1beta/files?upload_id=test"})
        if request.method == "GET":
            return httpx.Response(200, json={"name": "files/test-audio", "uri": API_ORIGIN + "/v1beta/files/test-audio", "state": "ACTIVE"})
        assert path.endswith(":generateContent")
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert body["contents"][0]["parts"][0]["fileData"]["mimeType"] == "audio/wav"
        return httpx.Response(self.generation_status, json=self.output)


async def run(api, settings, audio):
    async with httpx.AsyncClient(transport=httpx.MockTransport(api)) as client:
        return [update async for update in GeminiInstrumentClassifier(settings, client).analyze(audio, 6, .3)]


async def test_complete_audio_upload_once_and_remote_cleanup(gemini_settings, audio_file):
    api = GeminiAPI()
    updates = await run(api, gemini_settings, audio_file)
    assert isinstance(updates[0], AnalysisProgress)
    assert isinstance(updates[-1], ProviderResult)
    assert {i.name for i in updates[-1].windows[0].instruments} == {"Piano", "Drums"}
    uploads = [r for r in api.requests if "upload_id" in r.url.params]
    assert len(uploads) == 1 and uploads[0].content == audio_file.read_bytes()
    assert api.requests[-1].method == "DELETE"


@pytest.mark.parametrize("status", [400, 401, 403, 429, 503])
async def test_generation_errors_still_delete_upload(gemini_settings, audio_file, status):
    api = GeminiAPI(generation_status=status)
    result = (await run(api, gemini_settings, audio_file))[-1]
    assert result.windows[0].status == "failed" and result.windows[0].instruments == []
    assert "test-gemini-key" not in result.windows[0].error
    assert api.requests[-1].method == "DELETE"


async def test_malformed_output_still_deletes(gemini_settings, audio_file):
    api = GeminiAPI(output=generated({"segments": [segment(0, 9000, Piano=.8)]}))
    result = (await run(api, gemini_settings, audio_file))[-1]
    assert result.windows[0].status == "failed"
    assert api.requests[-1].method == "DELETE"


async def test_delete_failure_is_visible(gemini_settings, audio_file):
    api = GeminiAPI(delete_status=503)
    result = (await run(api, gemini_settings, audio_file))[-1]
    assert result.windows[0].status == "ok"
    assert any("could not be deleted" in warning for warning in result.warnings)


async def test_poll_processing(gemini_settings, audio_file, monkeypatch):
    async def sleep(_): pass
    monkeypatch.setattr("app.services.gemini_classifier.asyncio.sleep", sleep)
    api = GeminiAPI(processing=True)
    result = (await run(api, gemini_settings, audio_file))[-1]
    assert result.windows[0].status == "ok"
    assert any(r.method == "GET" for r in api.requests)


async def test_cancel_before_generation_deletes_upload(gemini_settings, audio_file):
    api = GeminiAPI()
    async with httpx.AsyncClient(transport=httpx.MockTransport(api)) as client:
        updates = GeminiInstrumentClassifier(gemini_settings, client).analyze(audio_file, 6, .3)
        assert (await anext(updates)).stage == "uploading_to_gemini"
        assert (await anext(updates)).stage == "analyzing_instruments"
        await updates.aclose()
    assert api.requests[-1].method == "DELETE"
    assert not any(r.url.path.endswith(":generateContent") for r in api.requests)


async def test_retries_timeout_and_rate_limit(gemini_settings, monkeypatch):
    gemini_settings.api_retries = 2
    calls, delays = [], []
    async def sleep(delay): delays.append(delay)
    monkeypatch.setattr("app.services.gemini_classifier.asyncio.sleep", sleep)
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ReadTimeout("test", request=request)
        if len(calls) == 2:
            return httpx.Response(429, headers={"retry-after": "3"})
        return httpx.Response(200, json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await GeminiInstrumentClassifier(gemini_settings, client)._request("GET", API_ORIGIN + "/v1beta/files/test")
    assert len(calls) == 3 and delays == [1, 3]


async def test_missing_key_and_untrusted_upload_url(gemini_settings):
    async with httpx.AsyncClient() as client:
        provider = GeminiInstrumentClassifier(gemini_settings, client)
        with pytest.raises(ProviderError, match="unexpected upload"):
            await provider._request("POST", "https://untrusted.example/upload")
        gemini_settings.gemini_api_key = type(gemini_settings.hf_token)("")
        with pytest.raises(ProviderError, match="GEMINI_API_KEY"):
            await provider._request("GET", API_ORIGIN + "/v1beta/files/test")
