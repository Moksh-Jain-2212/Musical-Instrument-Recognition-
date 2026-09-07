import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.hosted_classifier import ProviderError
from app.models.schemas import InstrumentPrediction, InstrumentWindow
from app.services.instrument_classifier import AnalysisProgress, ProviderResult
from app.services.labels import SUPPORTED_INSTRUMENTS
from tests.conftest import wav_bytes


class Classifier:
    def __init__(self, fail_at=None, fatal=False):
        self.calls = 0
        self.fail_at = fail_at
        self.fatal = fatal

    async def classify(self, wav):
        self.calls += 1
        assert wav.startswith(b"RIFF")
        if self.calls == self.fail_at:
            raise ProviderError("Test provider failure", fatal=self.fatal)
        return [{"label": "Piano", "score": .9}, {"label": "Drum", "score": .8}]


def test_health_and_static_no_model_or_token_needed():
    with TestClient(create_app(Settings(_env_file=None, hf_token=""))) as client:
        health = client.get("/health").json()
        assert health["status"] == "configuration_required"
        assert health["ffmpeg_available"]
        assert "hf_token" not in health
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/.env").status_code == 404
        response = client.post("/api/analyze", files={"file": ("a.wav", wav_bytes())})
        assert response.status_code == 503 and "HF_TOKEN" in response.json()["detail"]


def test_analyze_partial_failure_and_cleanup(settings, monkeypatch):
    import app.services.analysis as analysis
    actual = analysis.decode_audio
    paths = []
    def decode(source, output, settings):
        paths.extend([source, output])
        return actual(source, output, settings)
    monkeypatch.setattr(analysis, "decode_audio", decode)
    classifier = Classifier(fail_at=2)
    with TestClient(create_app(settings, classifier)) as client:
        response = client.post("/api/analyze", files={"file": ("music.wav", wav_bytes(11))})
        assert response.status_code == 200
        data = response.json()
        assert data["duration"] == 11 and data["failed_chunks"] == 1
        assert data["windows"][1]["status"] == "failed"
        assert len(data["instrument_tracks"]["Piano"]) == 2
        assert [item["name"] for item in data["timeline"][0]["instruments"]] == ["Drums", "Piano"]
    assert classifier.calls == 3
    assert all(not Path(path).exists() for path in paths)


def test_stream_progress_and_result(settings):
    with TestClient(create_app(settings, Classifier())) as client:
        response = client.post("/api/analyze/stream", files={"file": ("music.wav", wav_bytes(6))})
        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[0]["stage"] == "decoding"
        assert events[-2]["completed"] == events[-2]["total"] == 2
        assert events[-1]["type"] == "result"
        assert events[-1]["result"]["timeline"][0]["end"] == 6


def test_invalid_file_empty_threshold_and_released_lock(settings):
    with TestClient(create_app(settings, Classifier())) as client:
        for data in (b"", b"invalid audio"):
            assert client.post("/api/analyze", files={"file": ("a.wav", data)}).status_code == 400
        assert client.post("/api/analyze?threshold=2", files={"file": ("a.wav", wav_bytes())}).status_code == 422
        assert client.post("/api/analyze", files={"file": ("a.wav", wav_bytes())}).status_code == 200


def test_large_upload(settings):
    settings.max_upload_mb = 1
    with TestClient(create_app(settings, Classifier())) as client:
        assert client.post("/api/analyze", files={"file": ("large.wav", b"x" * 1200000)}).status_code == 413


def test_fatal_auth_does_not_send_remaining_chunks(settings):
    classifier = Classifier(fail_at=1, fatal=True)
    with TestClient(create_app(settings, classifier)) as client:
        response = client.post("/api/analyze", files={"file": ("a.wav", wav_bytes(11))})
        assert response.json()["failed_chunks"] == 3
        assert not any("No specific musical instrument" in warning for warning in response.json()["warnings"])
        assert classifier.calls == 1


def test_threshold_override(settings):
    with TestClient(create_app(settings, Classifier())) as client:
        result = client.post("/api/analyze?threshold=0.85", files={"file": ("a.wav", wav_bytes())}).json()
        assert [item["name"] for item in result["timeline"][0]["instruments"]] == ["Piano"]


def test_stream_error_releases_resources(settings):
    with TestClient(create_app(settings, Classifier())) as client:
        response = client.post("/api/analyze/stream", files={"file": ("bad.wav", b"bad")})
        assert json.loads(response.text.splitlines()[-1])["type"] == "error"
        assert client.post("/api/analyze", files={"file": ("ok.wav", wav_bytes())}).status_code == 200


def test_public_schema_and_health_are_instrument_only(settings):
    class MixedClassifier:
        async def classify(self, wav):
            return [{"label": name, "score": .95} for name in ("Music", "Speech", "Piano", "Drum", "Rock music")]
    with TestClient(create_app(settings, MixedClassifier())) as client:
        health = client.get("/health").json()
        assert health["provider"] == "yamnet"
        assert health["supported_instruments"] == list(SUPPORTED_INSTRUMENTS)
        assert "supported_events" not in health
        assert not {"Speech", "Music", "Silence", "Vocals", "Orchestra"} & set(health["supported_instruments"])
        result = client.post("/api/analyze", files={"file": ("a.wav", wav_bytes())}).json()
        assert set(result["instrument_tracks"]) == {"Piano", "Drums"}
        assert "instruments" not in result
        for window in result["windows"] + result["timeline"]:
            assert "events" not in window and "sounds" not in window
            assert {i["name"] for i in window["instruments"]} == {"Piano", "Drums"}


def test_no_specific_instrument_case(settings):
    class MusicOnly:
        async def classify(self, wav):
            return [{"label": "Music", "score": .99}, {"label": "Rock music", "score": .98}, {"label": "Song", "score": .95}]
    with TestClient(create_app(settings, MusicOnly())) as client:
        result = client.post("/api/analyze", files={"file": ("a.wav", wav_bytes())}).json()
        assert result["timeline"][0]["instruments"] == []
        assert result["instrument_tracks"] == {} and result["failed_chunks"] == 0
        assert any("No specific musical instrument" in warning for warning in result["warnings"])


def test_gemini_requires_its_key_not_hf_token(settings):
    settings.instrument_provider = "gemini"
    with TestClient(create_app(settings)) as client:
        health = client.get("/health").json()
        assert health["required_credential"] == "GEMINI_API_KEY"
        assert health["status"] == "configuration_required" and health["chunk_duration"] is None
        result = client.post("/api/analyze", files={"file": ("a.wav", wav_bytes())})
        assert result.status_code == 503 and "GEMINI_API_KEY" in result.json()["detail"]
        assert "hf_test_not_a_real_token" not in json.dumps(health)


def test_gemini_common_result_and_stream(settings):
    settings.instrument_provider = "gemini"
    settings.gemini_api_key = type(settings.hf_token)("gemini_test_key")
    settings.hf_token = type(settings.hf_token)("")
    paths = []
    class SemanticProvider:
        async def analyze(self, path, duration, threshold):
            paths.append(path)
            assert path.exists()
            yield AnalysisProgress("analyzing_instruments")
            yield ProviderResult([InstrumentWindow(start=0, end=duration,
                instruments=[InstrumentPrediction(name="Piano", confidence=.85)])], ["Semantic estimates"])
    with TestClient(create_app(settings, instrument_classifier=SemanticProvider())) as client:
        health = client.get("/health").json()
        assert health["status"] == "ready" and health["provider"] == "gemini"
        assert "gemini_test_key" not in json.dumps(health)
        response = client.post("/api/analyze/stream", files={"file": ("a.wav", wav_bytes(6))})
        messages = [json.loads(line) for line in response.text.splitlines()]
        assert any(m.get("stage") == "analyzing_instruments" for m in messages)
        result = messages[-1]["result"]
        assert result["provider"] == "gemini" and result["chunk_duration"] is None
        assert result["timeline"][0]["instruments"] == [{"name": "Piano", "confidence": .85}]
        assert set(result["instrument_tracks"]) == {"Piano"}
    assert all(not path.exists() for path in paths)
