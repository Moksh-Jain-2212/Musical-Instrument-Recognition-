# Musical Instrument Detector

Upload music to estimate **which musical instruments are audible at each timestamp**. This is the existing Sound Atlas project, updated in place with instrument-only results and the Instrument Timeline interface.

The app retains FastAPI, drag-and-drop audio upload, FFmpeg decoding, configurable confidence, temporary-file cleanup, streaming progress, the synchronized audio player, independent instrument tracks, and JSON download. It also includes an **Instruments Found** summary with each instrument's intervals and duration-weighted average score.

## Providers

Set `INSTRUMENT_PROVIDER` in `.env`, then restart. Both providers return the same instrument-oriented schema and use the same timeline/UI code. There is no automatic provider switching or paid fallback.

| Provider | Model / API | How it analyzes audio |
| --- | --- | --- |
| `yamnet` (default) | Google YAMNet v1 on the existing [Hugging Face Space](https://huggingface.co/spaces/thelou1s/yamnet) | Sequential 5-second chunks; filter direct instrument predictions above the threshold |
| `gemini` (optional) | `gemini-2.5-flash`, Google Gemini Files API + `generateContent` | Upload the complete decoded recording once; request structured JSON instrument intervals; validate, normalize and filter the response |

No ML model runs locally. No TensorFlow, PyTorch, GPU, or new SDK is required. The Gemini adapter uses the existing `httpx` dependency and Google's [audio understanding](https://ai.google.dev/gemini-api/docs/audio), [Files API](https://ai.google.dev/gemini-api/docs/files), and [generation API](https://ai.google.dev/api/generate-content).

**YAMNet was preserved after a successful live hosted test.** The public endpoint still returned HTTP 200 on a five-second synthetic silence probe. The model returned Silence, but the application now removes that label from instrument results. The original verification is recorded in [hosted-model-verification.md](docs/hosted-model-verification.md).

**Top-five restriction:** the current YAMNet host exposes only its five highest-scoring AudioSet labels per chunk, before our filtering. Music, genres, voices, or other broad labels can occupy those slots. Filtering them does not recover hidden instrument predictions. All qualifying returned instruments are retained; the app does not choose only the highest one.

Gemini is implemented and tested with mocked HTTP responses. A live Gemini inference has not been run as part of this update. Its output is a semantic estimate; it has no AudioSet-style fixed instrument classifier head.

## Installation and startup

Use **Python 3.11 or 3.12**. Development was tested with Python 3.12.3 on Linux. The existing virtual environment can be reused.

```bash
cd "/home/moksh/Sound deletection model"
# Only create the environment if you do not already have it:
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
# Only copy if .env does not already exist; preserve your existing keys:
cp -n .env.example .env
```

On Ubuntu, install `python3-venv` and `python3-pip` if needed. On Windows, use `py -3.12 -m venv .venv` and `.venv\Scripts\Activate.ps1`; copy `.env.example` manually only if `.env` is absent. With `uv`, use `uv venv --python 3.12` and `uv pip install -r requirements.txt`.

### Default: YAMNet

Create a free Hugging Face account and a **Read** token in [Settings → Access Tokens](https://huggingface.co/settings/tokens). Configure:

```dotenv
INSTRUMENT_PROVIDER=yamnet
HF_TOKEN=hf_your_actual_token
```

The application requires the token for normal analysis and sends it only from the backend to the selected HTTPS Space. No write permission is needed. This community Space is distinct from the generic Hugging Face Inference Providers service. See [Space API authentication](https://huggingface.co/docs/hub/spaces-api-endpoints).

### Optional: Gemini

Get a key for your project in [Google AI Studio](https://aistudio.google.com/apikey). Configure:

```dotenv
INSTRUMENT_PROVIDER=gemini
GEMINI_API_KEY=your_actual_key
GEMINI_MODEL=gemini-2.5-flash
```

Only the selected provider's credential is required. Gemini does not require `HF_TOKEN`; YAMNet does not require `GEMINI_API_KEY`. Keep credentials in `.env`, which is gitignored; never add them to HTML/JavaScript or commit them. Existing `.env` values are preserved by this update.

Use an eligible free-tier project if you want free Gemini access. Availability and limits depend on the project, region, and model; check [current pricing](https://ai.google.dev/gemini-api/docs/pricing) and [rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). If you supply a key attached to paid billing, usage follows that project's billing settings. The app does not enable billing, purchase capacity, or change providers after an error.

### FFmpeg

`imageio-ffmpeg` supplies an FFmpeg binary on supported platforms. The existing lookup order is: `FFMPEG_PATH`, system FFmpeg, then the bundled binary. No model weights are downloaded.

For a system installation:

```bash
# Ubuntu / Debian
sudo apt update
sudo apt install ffmpeg

# macOS with Homebrew
brew install ffmpeg

# Windows with winget
winget install Gyan.FFmpeg
```

Set an absolute `FFMPEG_PATH` if your executable is not discoverable. Restart your terminal after modifying PATH.

### Run

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Upload WAV, MP3, M4A, or WebM, adjust the confidence slider, then select **Analyze Instruments**. Listen with the audio player: the playhead, highlighted tracks, current instruments and scores follow `audio.currentTime`. Click a timeline segment, table timestamp, or summary interval to seek. Download JSON to retain results.

Browser playback depends on codec support. If a file can be analyzed but not played, convert it to MP3 or PCM WAV for synchronization. This version analyzes uploaded recordings.

## Supported instruments

YAMNet exposes **61 normalized instrument labels** through the allowlist. Every source name is validated against its real 521-label vocabulary. Expand **Supported instruments** on the page to see the selected provider's names, or see the [complete source-to-display mapping](docs/supported-instruments.md).

- **Keyboards:** Piano, Electric Piano, Keyboard, Organ, Electronic Organ, Hammond Organ, Synthesizer, Sampler, Harpsichord.
- **Guitars and plucked strings:** Guitar, Acoustic Guitar, Electric Guitar, Bass Guitar, Steel / Slide Guitar, Ukulele, Banjo, Sitar, Mandolin, Zither, Harp, Plucked Strings.
- **Drums and percussion:** Drums, Snare Drum, Bass Drum, Drum Machine, Cymbal, Hi-Hat, Percussion, Tabla, Timpani, Tambourine, Maraca, Rattle, Gong, Wood Block, Tubular Bells, Mallet Percussion, Marimba / Xylophone, Glockenspiel, Vibraphone, Steelpan, Singing Bowl.
- **Bowed strings:** Violin, Cello, Double Bass, Bowed String Instrument, String Section.
- **Wind and brass:** Flute, Clarinet, Saxophone, Trumpet, Trombone, French Horn, Harmonica, Accordion, Bagpipes, Didgeridoo, Shofar, Brass Instrument, Woodwind Instrument.
- **Other:** Theremin.

`Drum` and `Drum kit` become `Drums`; `Violin, fiddle` becomes `Violin`; `Keyboard (musical)` becomes `Keyboard`. For multiple aliases, use the maximum score, not the sum. The combined `Marimba, xylophone` class remains combined: the app cannot distinguish those instruments from that prediction. Viola is not supported by this YAMNet mapping.

Gemini is constrained to these same display names plus **Strings**, **Woodwinds**, and **Brass** as broad instrument families. This is the application's output vocabulary, not a guarantee that Gemini recognizes every instrument. Unsupported generated names are discarded after validation.

**Removed from all detection results:** Speech, Conversation, Singing/Vocals, Choir, Humming, Rapping, Music, Song, genres, Silence, environmental/human sounds, animals, vehicles, Orchestra, and Musical instrument / Instrument (unspecified). Nothing maps a genre to an instrument. Singing Bowl remains allowed because it is an actual instrument. The bundled full YAMNet label file is retained for validating the hosted response, not for exposing general labels.

If no direct instrument prediction passes the threshold, the interval has `instruments: []`. The UI says **“No specific musical instrument was confidently detected in this interval.”** It never fabricates an instrument, an Instrumental label, or silence. Failed analysis is displayed separately.

## Configuration

| Setting | Default | Meaning |
| --- | --- | --- |
| `INSTRUMENT_PROVIDER` | `yamnet` | `yamnet` or `gemini`; only selected provider is called |
| `HF_TOKEN` | empty | YAMNet hosted Space access token |
| `GEMINI_API_KEY` | empty | Gemini API key |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Audio-capable Gemini model with structured-output support |
| `CHUNK_DURATION` | `5` | YAMNet seconds per nonoverlapping chunk; 3–10 allowed |
| `CONFIDENCE_THRESHOLD` | `0.30` | Inclusive minimum score, adjustable per analysis in the UI |
| `API_TIMEOUT_SECONDS` | `45` | Per-request timeout; also Gemini file-preparation wait budget |
| `API_RETRIES` | `2` | Extra attempts for transient HTTP errors; maximum 3 |
| `MAX_UPLOAD_MB` | `100` | Maximum uploaded file size |
| `MAX_DURATION_SECONDS` | `900` | Maximum audio duration, default 15 minutes |
| `FFMPEG_PATH` | empty | Optional absolute FFmpeg executable path |

Restart after changing `.env`. For Gemini, a longer `API_TIMEOUT_SECONDS` (up to 180) may help with whole recordings. A 0.20 confidence threshold is more permissive; 0.50 is more selective. Scores from either provider are **not guaranteed probabilities of correctness**, and scores from the two providers are not calibrated against one another.

## Timestamp behavior

**YAMNet:** decode once to mono 16 kHz PCM16, then send 0–5, 5–10, 10–15 seconds, etc. The final chunk ends at actual decoded duration. A 60-second file makes 12 initial requests at the default setting; retries can add calls. Hosted frame-average scores are filtered to the instrument allowlist and threshold. This update retains efficient nonoverlapping windows; optional overlapping requests were not added because they increase use of the shared host.

**Gemini:** upload the complete normalized recording using the Files API, wait for it to become active, then send one structured instrument-analysis request. Numeric timestamps and scores are validated; invalid ranges, nonfinite scores, blocked output or truncated JSON become visible failures. Tiny end-time rounding (at most 0.1 second) is clamped to actual duration; larger out-of-range values are rejected. Overlapping reported segments are split at every boundary and combined with maximum confidence per instrument. Gaps remain empty, with no guessed instruments.

Both providers feed the same merging code:

1. **Chronological timeline:** adjacent intervals merge only if instrument sets and status match. Scores are duration-weighted averages.
2. **Independent instrument tracks:** continuous presence merges even when other instruments enter or leave. Failed or empty intervals break a track.
3. **Summary:** lists every continuous interval per instrument; overall confidence is weighted by detected duration, excluding gaps.

Intervals use `[start, end)` so playback switches at boundaries. The current display uses the unmerged normalized windows and their scores. Showing tenths of a second on the player does not imply the model has that timing accuracy.

## API

- `GET /health`: selected provider/model, credential configuration state, FFmpeg availability, settings and `supported_instruments`. Never returns key values. `ready` means locally configured; remote availability/key validity is not checked by this endpoint.
- `POST /api/analyze`: multipart `file`, optional `threshold` query parameter; returns a complete JSON result.
- `POST /api/analyze/stream`: same inputs, newline-delimited JSON progress/result/error messages. YAMNet reports completed chunks; Gemini reports upload/preparation/analysis stages without a fabricated percentage.
- `GET /docs`: interactive API documentation.

```bash
curl -X POST 'http://127.0.0.1:8000/api/analyze?threshold=0.30' \
  -F 'file=@/path/to/music.mp3'
```

Public schema (illustrative excerpt):

```json
{
  "duration": 10,
  "timeline": [
    {"start": 0, "end": 5, "instruments": [{"name": "Piano", "confidence": 0.88}], "status": "ok"},
    {"start": 5, "end": 10, "instruments": [{"name": "Drums", "confidence": 0.79}, {"name": "Piano", "confidence": 0.84}], "status": "ok"}
  ],
  "instrument_tracks": {
    "Piano": [{"start": 0, "end": 10, "average_confidence": 0.86}],
    "Drums": [{"start": 5, "end": 10, "average_confidence": 0.79}]
  },
  "provider": "yamnet",
  "model": "Google YAMNet v1 (AudioSet, 521 labels)",
  "threshold": 0.3,
  "chunk_duration": 5,
  "failed_chunks": 0
}
```

Actual responses also contain `windows` (same instrument objects plus per-interval `status` and `error`) and `warnings`. Gemini returns `chunk_duration: null`. The retained `failed_chunks` counter counts failed normalized intervals, including one whole-file interval if Gemini fails.

**Schema migration:** old `timeline[].events`, separate `confidences`, and `windows[].events` are replaced by `instruments: [{name, confidence}]`; the old top-level track dictionary `instruments` is now `instrument_tracks`. `/health.supported_events` is now `supported_instruments`. The frontend and existing tests were updated together. External consumers of the old Sound Atlas JSON must update these field names.

## Errors, retries and cleanup

The existing upload/decoding errors, size/duration limits, request lock, and cleanup remain. Invalid or empty audio returns 400; oversized uploads return 413; a missing selected-provider credential returns 503; a busy analyzer returns 429. Use one Uvicorn worker to retain the intended single-analysis limit. Once an HTTP stream has begun, application errors are NDJSON error messages rather than a changed HTTP status. If every provider interval fails, the response reports failure without also claiming that no instrument was detected.

Canceling during FFmpeg decoding waits for the decoder worker to finish (subject to its existing 120-second timeout) before deleting its files. The canceled analysis does not proceed to classification, and upload-file closure is protected from cancellation. A new analysis may remain busy until that cleanup finishes.

YAMNet retries transient network/timeouts/rate-limit/server failures with bounded backoff and retains partial results. Fatal authentication/configuration errors stop further remote calls. Failed intervals stay explicitly failed, even if every interval fails.

Gemini retries transient setup, polling and generation requests with bounded backoff. The final upload body is sent once and is not blindly replayed after an ambiguous timeout. Generation retries reuse the uploaded file; they can consume additional quota. Invalid semantic output is reported as failure, not guessed or silently repaired into plausible instruments.

Temporary local upload and decoded files are removed after completion, failure, or cancellation; short YAMNet chunks exist only in memory. Gemini uploads are deleted in a `finally` block, including cancellation after an upload is known. Deletion failure is warned about. An upload accepted remotely but whose identifier is lost to a network failure cannot be explicitly deleted; Google's [documented Files API expiration](https://ai.google.dev/gemini-api/docs/files) is the fallback (normally 48 hours). Provider retention policies may apply beyond this temporary file lifecycle.

The YAMNet community Space can cache uploads or log requests; this application cannot guarantee remote deletion there. Gemini receives the complete recording and is subject to Google's data-use terms for your project/tier. The UI identifies the selected destination. The app does not permanently store a local music library or expose API keys to the browser.

## Accuracy and free access limitations

Instrument recognition in mixed/polyphonic music is difficult. Both providers can confuse similar instruments, miss quiet/background instruments, return broad instrument families, and estimate approximate time ranges. YAMNet's top-five output cap can hide instruments entirely. Gemini's names, timestamps, and self-reported scores are semantic estimates and can be wrong. Neither provider is an accuracy guarantee, and this project's tests validate software behavior rather than recognition accuracy.

The existing public YAMNet Space was callable for free during verification. It is community demo access with no guaranteed request allowance, uptime, or latency; it may sleep, stop, rate-limit requests, or change its API. It is not backed by a promised Inference Providers free-tier quota. Gemini has project/model-specific quotas and billing settings; free key creation is not unlimited free inference. The default remains YAMNet and no automatic paid replacement is enabled.

## Tests and verification

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check app/static/app.js
python -m compileall -q app scripts
```

Tests block real outbound provider traffic and use mocked Gemini/Hugging Face responses. They cover the original audio formats, downmix/resampling, timestamps, limits, upload cleanup and progress, plus the instrument allowlist, removed labels, aliases, multiple instruments, independent tracks, Gemini JSON validation, overlapping segments, gap handling, retries, authentication errors, and remote deletion after failure/cancellation.

Continuation verification on 2026-09-07: **112 tests passed**, with two existing test-client dependency deprecation warnings. JavaScript syntax, Python compilation, and diff whitespace checks passed. FastAPI started successfully; `/health` reported ready. A live five-second synthetic-silence upload through `/api/analyze` returned one successful empty instrument interval and no failed chunks. Browser visual verification was unavailable because no browser was connected. Gemini remains verified with mocked responses, not live inference.

The current host can be checked separately using synthetic silence only:

```bash
python -m scripts.verify_hosted --public-probe  # anonymous public test
python -m scripts.verify_hosted                 # use HF_TOKEN from .env
```

These commands make real Hugging Face requests; they are not unit tests. The script intentionally prints raw model labels for verification, whereas the application's analysis responses contain only instruments. No live Gemini call is part of the test suite. `requirements-lock.txt` remains the existing tested dependency snapshot; no new packages were necessary for this update.

## Modified architecture

- `app/config.py`, `.env.example`: provider choice and separate credentials/model setting.
- `app/models/schemas.py`: instrument-oriented predictions, windows and tracks.
- `app/services/labels.py`: direct instrument allowlist, normalization and Gemini output vocabulary.
- `app/services/instrument_classifier.py`: shared provider interface and progress/result messages.
- `app/services/yamnet_classifier.py`: existing chunk loop moved behind that interface, reusing `hosted_classifier.py`.
- `app/services/gemini_classifier.py`: optional whole-recording API integration, validation and cleanup.
- `app/services/analysis.py`: reused upload/decoding lifecycle, common provider orchestration.
- `app/services/timeline_processor.py`: reused merging and independent tracks with instrument fields.
- `app/main.py`: provider selection, health metadata and updated response schemas.
- `app/static/index.html`, `app.js`, `style.css`: instrument branding, synchronized result fields, provider status and instrument summary.
- `tests/`: existing tests retained and updated, with instrument filtering and mocked Gemini coverage added.
- `docs/supported-instruments.md`: complete mapping; `docs/hosted-model-verification.md`: historical verification plus instrument-only update.

`app/services/audio_processing.py`, the hosted YAMNet HTTP adapter, the full source label vocabulary, and dependency requirements are reused unchanged.
