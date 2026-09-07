import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app
from app.services.hosted_classifier import HostedClassifier
from app.services.timeline_processor import merge_timeline
from app.services.yamnet_classifier import instrument_window
from tests.conftest import wav_bytes


RAW = [
    {"label": "Music", "score": .91},
    {"label": "Speech", "score": .80},
    {"label": "Piano", "score": .68},
    {"label": "Song", "score": .40},
    {"label": "Drum", "score": .17},
]


def test_default_configuration():
    settings = Settings(_env_file=None)
    assert settings.confidence_threshold == .20
    assert settings.instrument_fallback_enabled is False


@pytest.mark.parametrize("threshold", [0, .049, .801, 1, 20, float("nan"), float("inf")])
def test_config_rejects_invalid_threshold(threshold):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, confidence_threshold=threshold)


@pytest.mark.parametrize("route", ["/api/analyze", "/api/analyze/stream"])
@pytest.mark.parametrize("threshold", [.049, .801, 1, 20, "nan"])
def test_endpoints_reject_invalid_threshold_without_inference(settings, route, threshold):
    class NoCalls:
        async def classify(self, wav):
            pytest.fail("Invalid threshold must not call the provider")

    with TestClient(create_app(settings, NoCalls())) as client:
        response = client.post(f"{route}?threshold={threshold}", files={"file": ("a.wav", wav_bytes())})
    assert response.status_code == 422


@pytest.mark.parametrize("route", ["/api/analyze", "/api/analyze/stream"])
def test_real_adapter_preserves_top_five_per_chunk(settings, route):
    calls = []

    def handler(request):
        calls.append(request)
        labels = ", ".join(f'[{p["label"]}]' for p in RAW)
        scores = ", ".join(f'[{p["score"]}]' for p in RAW)
        return httpx.Response(200, json={"data": [f"classes: {labels}, scores: {scores}"]})

    # Exercise the existing parser as well as provider, orchestration and API serialization.
    transport_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with TestClient(create_app(settings, HostedClassifier(settings, transport_client))) as client:
        assert client.get("/health").json()["confidence_threshold"] == .2
        response = client.post(route, files={"file": ("music.wav", wav_bytes(11))})
        client.portal.call(transport_client.aclose)
    assert response.status_code == 200
    data = response.json() if route == "/api/analyze" else json.loads(response.text.splitlines()[-1])["result"]
    assert data["threshold"] == .2 and data["fallback_enabled"] is False
    assert len(calls) == 3
    assert [(w["start"], w["end"]) for w in data["windows"]] == [(0, 5), (5, 10), (10, 11)]
    for window in data["windows"]:
        assert window["raw_predictions"] == RAW
        assert window["instruments"] == [{"name": "Piano", "confidence": .68}]
        assert window["effective_threshold"] == .2 and not window["fallback_used"]
    assert set(data["instrument_tracks"]) == {"Piano"}
    assert data["timeline"][0]["end"] == 11


@pytest.mark.parametrize("threshold", [.05, .80])
def test_threshold_boundaries_accepted(settings, threshold):
    class Scores:
        async def classify(self, wav):
            return [{"label": "Piano", "score": threshold}]

    with TestClient(create_app(settings, Scores())) as client:
        response = client.post(f"/api/analyze?threshold={threshold}", files={"file": ("a.wav", wav_bytes())})
    assert response.status_code == 200
    assert response.json()["windows"][0]["instruments"][0]["confidence"] == threshold


@pytest.mark.parametrize("fallback,expected", [(False, []), (True, [{"name": "Drums", "confidence": .17}])])
@pytest.mark.parametrize("route", ["/api/analyze", "/api/analyze/stream"])
def test_optional_fallback_reuses_predictions(settings, fallback, expected, route):
    raw = [dict(p, score=.1) if p["label"] == "Piano" else p for p in RAW]

    class Scores:
        calls = 0
        async def classify(self, wav):
            self.calls += 1
            return raw

    scores = Scores()
    with TestClient(create_app(settings, scores)) as client:
        response = client.post(f"{route}?fallback={str(fallback).lower()}", files={"file": ("a.wav", wav_bytes(6))})
    data = response.json() if route == "/api/analyze" else json.loads(response.text.splitlines()[-1])["result"]
    assert scores.calls == 2  # One request per chunk even with fallback enabled.
    assert data["threshold"] == .2 and data["fallback_enabled"] is fallback
    for window in data["windows"]:
        assert window["raw_predictions"] == raw
        assert window["instruments"] == expected
        assert window["fallback_used"] is fallback
        assert window["effective_threshold"] == (.15 if fallback else .2)


def test_fallback_config_can_be_overridden_per_request(settings):
    settings.instrument_fallback_enabled = True
    class Scores:
        async def classify(self, wav):
            return [{"label": "Piano", "score": .15}]
    with TestClient(create_app(settings, Scores())) as client:
        assert client.get("/health").json()["instrument_fallback_enabled"] is True
        enabled = client.post("/api/analyze", files={"file": ("a.wav", wav_bytes())}).json()
        disabled = client.post("/api/analyze?fallback=false", files={"file": ("a.wav", wav_bytes())}).json()
    assert enabled["windows"][0]["instruments"] == [{"name": "Piano", "confidence": .15}]
    assert disabled["windows"][0]["instruments"] == []


@pytest.mark.parametrize("threshold", [.05, .15, .2])
def test_fallback_does_not_raise_threshold_or_expand_successful_window(threshold):
    window = instrument_window(0, 5, RAW, threshold, fallback=True)
    assert window.effective_threshold == threshold
    assert not window.fallback_used
    assert {i.name for i in window.instruments} == ({"Piano", "Drums"} if threshold <= .15 else {"Piano"})


@pytest.mark.parametrize("label,score,message", [
    ("Music", .9, "detected music"), ("Rock music", .9, "detected music"),
    ("Song", .9, "detected music"), ("Music", .1, "None of YAMNet"),
    ("Piano", .1, "None of YAMNet"), ("Speech", .9, "Only non-instrument"),
])
def test_empty_window_explanation(label, score, message):
    window = instrument_window(0, 5, [{"label": label, "score": score}], .2)
    assert window.instruments == [] and message in window.message


def test_fallback_never_invents_instruments_and_reports_attempt():
    window = instrument_window(0, 5, [{"label": "Rock music", "score": .9}], .2, fallback=True)
    assert window.instruments == []
    assert window.fallback_used and window.effective_threshold == .15
    assert "15%" in window.message


def test_merging_keeps_distinct_diagnostics_and_fallback_status():
    windows = [instrument_window(0, 5, [{"label": "Music", "score": .9}], .2),
               instrument_window(5, 10, [{"label": "Music", "score": .1}], .2)]
    assert len(merge_timeline(windows)) == 2
    normal = instrument_window(0, 5, [{"label": "Piano", "score": .3}], .2, True)
    fallback = instrument_window(5, 10, [{"label": "Piano", "score": .17}], .2, True)
    merged = merge_timeline([normal, fallback])
    assert len(merged) == 2 and merged[1].fallback_used
