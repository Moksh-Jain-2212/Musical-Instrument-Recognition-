# Hosted model verification

Checked on 2026-09-07 before implementing the application.

## Selection

- API: Hugging Face **Spaces** HTTP API, `https://thelou1s-yamnet.hf.space/api/predict`.
- Running host: [`thelou1s/yamnet`](https://huggingface.co/spaces/thelou1s/yamnet).
- Model: Google YAMNet v1, loaded on the remote server from `https://tfhub.dev/google/yamnet/1`.
- API version inspected: Gradio 3.2; `/config` exposes `predict`, and `/openapi.json` requires `session_hash` and `data`.
- Source revision reported by the Hub: `7884023131c000d36cec4d8dbc791083f8c3f126`.
- [Inspected host source](https://huggingface.co/spaces/thelou1s/yamnet/blob/7884023131c000d36cec4d8dbc791083f8c3f126/app.py): averages YAMNet's independent class scores over frames, then returns five labels and their scores. This is multi-label scoring, not softmax classification.

The live public POST with five seconds of generated PCM16 silence returned HTTP 200:

```json
{
  "data": ["The main sound is: [Silence], \n\nthe second sound is: [Speech]. \n\n classes: [Silence], [Speech], [Music], [Inside, small room], [Narration, monologue], \n\n scores: [1.0000], [0.0000], [0.0000], [0.0000], [0.0000]"]
}
```

This verifies a functioning hosted prediction, not instrument accuracy. No real user music was used for this probe. No valid user token was available during development, so a real authenticated request has **not** been tested. Header transmission and authentication-error handling are covered by mocked transport tests. Hugging Face [documents bearer-token access to Space APIs](https://huggingface.co/docs/hub/spaces-api-endpoints). The application requires `HF_TOKEN`; the synthetic verification script additionally supports an explicit public probe.

## Why not the generic Hugging Face Inference API?

The [current audio-classification task documentation](https://huggingface.co/docs/inference-providers/tasks/audio-classification) says no providers support the task. A live request to `https://huggingface.co/api/models/MIT/ast-finetuned-audioset-10-10-0.4593?expand=inferenceProviderMapping` returned an empty mapping. An available model download does not imply a callable serverless model.

The official `tensorflow/yamnet` Space reported a runtime error. The selected community Space reported RUNNING and completed a live request. Its top-five restriction is a material recall limitation; it is disclosed in the interface and every API result. It is a practical free demonstration service, not a guaranteed production endpoint.

## Labels and costs

The full 521-label list comes from [Google's YAMNet class map](https://github.com/tensorflow/models/blob/master/research/audioset/yamnet/yamnet_class_map.csv). The checked-in JSON is that list in original index order. `labels.py` only maps exact entries from it; startup validates that every mapped source name exists.

The selected public Space was callable without a payment or token in the probe. It publishes no guaranteed requests-per-day allocation or service-level agreement. It can sleep, stop, be rate-limited, or change its API. This is separate from Hugging Face Inference Providers credits. Do not interpret CPU Basic's free hourly price as guaranteed free creation of new Spaces: the [current overview](https://huggingface.co/docs/hub/spaces-overview) distinguishes paid-plan creation requirements from hourly compute cost.

Re-run verification with `python -m scripts.verify_hosted` after configuring `.env`, or `python -m scripts.verify_hosted --public-probe` for a token-free synthetic check.

## Instrument-only update (2026-09-07)

Continuation check on the same date: the public synthetic probe again succeeded. An authenticated end-to-end request through the running FastAPI `/api/analyze` endpoint also succeeded using five seconds of generated silence and the configured credential. The response contained `duration: 5`, `provider: "yamnet"`, one `status: "ok"` interval with `instruments: []`, empty `instrument_tracks`, and `failed_chunks: 0`. This closes the earlier authenticated-request verification gap; it does not establish instrument-recognition accuracy. No user music was uploaded and no credentials were printed.

Before modifying the provider flow, the same public synthetic-silence probe was rerun successfully: Space RUNNING, Gradio 3.2, HTTP 200, Silence 1.0000. YAMNet remains the default, with the same hosted API adapter. The new public results filter all non-instrument predictions; see [the 61-instrument mapping](supported-instruments.md). The raw silence response above is historical diagnostic evidence, not an example of the new public result.

An optional Gemini adapter now uses Google's documented [Files API](https://ai.google.dev/gemini-api/docs/files) and [generateContent API](https://ai.google.dev/api/generate-content). The default is `gemini-2.5-flash`, listed without an announced shutdown in Google's [deprecation table](https://ai.google.dev/gemini-api/docs/deprecations) at review time. Gemini uploads, structured JSON, retries, validation, and cleanup are tested with mocked responses; no live Gemini inference was performed for this update. Check current [pricing and free-tier eligibility](https://ai.google.dev/gemini-api/docs/pricing) for your project before selecting it.
