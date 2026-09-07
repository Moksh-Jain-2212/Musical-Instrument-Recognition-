import json

import httpx
import pytest

from app.services.hosted_classifier import HostedClassifier, ProviderError, parse_prediction


def test_parse_real_shape(valid_response):
    result = parse_prediction(valid_response)
    assert len(result) == 5
    assert result[1] == {"label": "Piano", "score": .91}


@pytest.mark.parametrize("payload", [None, {}, {"data": []}, {"data": [None]}, {"data": ["invalid"]},
                                     {"data": ["classes: [Piano], scores: [NaN]"]}])
def test_invalid_response(payload):
    with pytest.raises(ProviderError, match="invalid response"):
        parse_prediction(payload)


@pytest.mark.parametrize("bad", ["NaN", "inf", "-0.1", "1.2"])
def test_bad_scores(valid_response, bad):
    valid_response["data"][0] = valid_response["data"][0].replace("0.95", bad)
    with pytest.raises(ProviderError):
        parse_prediction(valid_response)


async def test_authorization_and_payload(settings, valid_response):
    def handler(request):
        assert request.headers["authorization"] == "Bearer hf_test_not_a_real_token"
        data = json.loads(request.content)
        assert data["session_hash"] and data["fn_index"] == 0
        assert data["data"][0]["data"].startswith("data:audio/wav;base64,")
        return httpx.Response(200, json=valid_response)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert len(await HostedClassifier(settings, client).classify(b"audio")) == 5


async def test_retry_rate_limit(settings, valid_response, monkeypatch):
    settings.api_retries = 2
    calls, sleeps = [], []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "2"}) if len(calls) < 3 else httpx.Response(200, json=valid_response)
    async def sleep(delay): sleeps.append(delay)
    monkeypatch.setattr("app.services.hosted_classifier.asyncio.sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await HostedClassifier(settings, client).classify(b"audio")
    assert len(calls) == 3 and sleeps == [2, 2]


@pytest.mark.parametrize("status,fatal", [(401, True), (403, True), (404, True), (429, False), (503, False)])
async def test_http_errors(settings, status, fatal):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(status))) as client:
        with pytest.raises(ProviderError) as error:
            await HostedClassifier(settings, client).classify(b"audio")
    assert error.value.fatal == fatal


async def test_timeout(settings):
    def handler(request): raise httpx.ReadTimeout("timeout", request=request)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError, match="timed out"):
            await HostedClassifier(settings, client).classify(b"audio")


async def test_missing_token(settings):
    settings.hf_token = type(settings.hf_token)("")
    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderError, match="HF_TOKEN"):
            await HostedClassifier(settings, client).classify(b"audio")
