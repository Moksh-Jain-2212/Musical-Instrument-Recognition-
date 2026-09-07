import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.hosted_classifier import ProviderError
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
        assert len(data["instruments"]["Piano"]) == 2
        assert data["timeline"][0]["events"] == ["Drums", "Piano"]
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
        assert classifier.calls == 1


def test_threshold_override(settings):
    with TestClient(create_app(settings, Classifier())) as client:
        result = client.post("/api/analyze?threshold=0.85", files={"file": ("a.wav", wav_bytes())}).json()
        assert result["timeline"][0]["events"] == ["Piano"]


def test_stream_error_releases_resources(settings):
    with TestClient(create_app(settings, Classifier())) as client:
        response = client.post("/api/analyze/stream", files={"file": ("bad.wav", b"bad")})
        assert json.loads(response.text.splitlines()[-1])["type"] == "error"
        assert client.post("/api/analyze", files={"file": ("ok.wav", wav_bytes())}).status_code == 200
