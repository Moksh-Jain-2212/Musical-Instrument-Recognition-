# Sound Atlas

A Python/FastAPI application that uploads one audio file, splits it into short chunks, calls a **real hosted YAMNet model**, and displays instruments, vocals, speech, music, and silence on a synchronized timeline. No local ML model, GPU, PyTorch, or TensorFlow installation is needed.

## API and model choice

**API:** the [Hugging Face Space `thelou1s/yamnet`](https://huggingface.co/spaces/thelou1s/yamnet), using its HTTP prediction API. **Model:** Google's [YAMNet v1](https://www.tensorflow.org/hub/tutorials/yamnet), trained on 521 AudioSet classes with independent multi-label outputs.

This is a community-hosted **Space**, not the generic Hugging Face serverless Inference Providers API. The latter currently has no audio-classification provider according to its [task documentation](https://huggingface.co/docs/inference-providers/tasks/audio-classification). We verified the running Space, inspected its code and labels, and successfully classified a generated five-second silence clip before implementation. See [the verification record](docs/hosted-model-verification.md).

**Material limitation:** this host returns its top **five** labels and scores per chunk, including non-musical categories. The app retains every supported label above your threshold from those five. It cannot retrieve the other 516 scores. Broad classes such as Music can occupy returned slots, so a busy mix may have undetected instruments. Scores are averaged over the chunk by the host. A 5-second window gives approximate 5-second boundaries, not precise note onsets. Nothing in this app identifies songs, artists, or albums.

## Run locally

Use **Python 3.11 or 3.12**; development was tested with Python 3.12.3 on Linux.

```bash
cd "/home/moksh/Sound deletection model"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

On Ubuntu, if the venv command is unavailable, install `python3-venv` and `python3-pip` with your system package manager. On Windows, use `py -3.12 -m venv .venv` and `.venv\Scripts\Activate.ps1`; copy `.env.example` to `.env` using `Copy-Item`. If you use `uv`, the equivalent is `uv venv --python 3.12` followed by `uv pip install -r requirements.txt`.

### Get the free token

1. Create a free account at [Hugging Face](https://huggingface.co/join).
2. Open [Settings → Access Tokens](https://huggingface.co/settings/tokens), select **Create new token**, and create a **Read** token for this application. No write permission is needed. [Token documentation](https://huggingface.co/docs/hub/security-tokens).
3. Edit your local `.env` and set `HF_TOKEN=hf_your_actual_token`.
4. Never place the token in frontend JavaScript or commit `.env`. The backend sends it as a bearer token only to the selected HTTPS Space. Restart the server after changes.

The production analyze endpoints require a token and report a helpful 503 error if it is missing. The public Space also accepts anonymous calls, which the separate synthetic verification script uses only when explicitly requested. A real authenticated inference cannot be validated until you provide your token in `.env`.

### FFmpeg

The included `imageio-ffmpeg` dependency supplies an FFmpeg binary on supported platforms. The app first checks `FFMPEG_PATH`, then system FFmpeg, then this bundled executable. No ML weights are downloaded.

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

Restart your terminal after adding FFmpeg to PATH. Alternatively set the absolute executable path in `.env`, e.g. `FFMPEG_PATH=/usr/bin/ffmpeg`.

### Start

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Choose or drop a WAV, MP3, M4A, or WebM file, set the confidence threshold, and click **Analyze audio**. Progress shows completed chunk requests. Play the audio or click a timeline segment to seek; the playhead and current sounds follow `audio.currentTime`. The table summarizes consecutive matching event sets. Download JSON for all raw windows, merged intervals, scores, and failures.

If the browser cannot play a particular codec/container, analysis can still succeed. Use MP3 or PCM WAV for the widest playback compatibility. This version accepts uploaded recordings; capture microphone audio in your recording app and upload it.

## Configuration

| `.env` setting | Default | Meaning |
| --- | --- | --- |
| `HF_TOKEN` | empty | Hugging Face token; required to analyze |
| `CHUNK_DURATION` | `5` | Seconds per nonoverlapping chunk, from 3 to 10 |
| `CONFIDENCE_THRESHOLD` | `0.30` | Keep returned labels at or above this score |
| `API_TIMEOUT_SECONDS` | `45` | Timeout per hosted HTTP request |
| `API_RETRIES` | `2` | Additional attempts for transient failures, maximum 3 |
| `MAX_UPLOAD_MB` | `100` | Maximum uploaded file size |
| `MAX_DURATION_SECONDS` | `900` | Maximum audio duration, default 15 minutes |
| `FFMPEG_PATH` | empty | Optional absolute FFmpeg executable path |

The UI slider overrides the threshold per analysis without modifying `.env`. A threshold of 0.20 finds more possible sounds and usually more false positives; 0.50 is more selective. These are model confidence scores, **not calibrated probabilities of correctness**. The selected host rounds scores to four decimal places.

Five-second chunks mean 12 initial calls for 60 seconds, or 60 for five minutes. Retries add calls, so they are capped. Requests are sequential, with one analysis at a time per server process to avoid flooding a shared service. Run one Uvicorn worker for these intended limits. Cancellation closes the local connection and releases temporary files; an already submitted remote request may still finish.

## Supported sounds

The application exposes **69 clean labels** from YAMNet's real label vocabulary. `GET /health` returns the current list; [labels.py](app/services/labels.py) contains the exact mapping and [yamnet_labels.json](app/models/yamnet_labels.json) contains all 521 original names.

- Strings: Piano, Electric piano, Guitar, Acoustic guitar, Electric guitar, Bass guitar, Steel / Slide guitar, Violin, Cello, Double bass, Harp, Ukulele, Banjo, Sitar, Mandolin, Zither, Plucked strings, Bowed string instrument, String section.
- Keyboards and electronics: Keyboard, Organ, Electronic organ, Hammond organ, Synthesizer, Sampler, Harpsichord, Theremin.
- Drums and percussion: Drums, Snare drum, Bass drum, Drum machine, Cymbal, Hi-hat, Percussion, Tabla, Timpani, Tambourine, Maraca, Rattle, Wood block, Gong, Tubular bells, Mallet percussion, Marimba / Xylophone, Glockenspiel, Vibraphone, Steelpan, Singing bowl.
- Winds and brass: Flute, Clarinet, Saxophone, Trumpet, Trombone, French horn, Harmonica, Accordion, Bagpipes, Didgeridoo, Shofar, Brass instrument, Woodwind instrument.
- Other: Vocals (from Singing, Choir, Vocal music, or A capella), Humming, Rapping, Speech, Music, Silence, Orchestra, Instrument (unspecified).

`Drum` and `Drum kit` map to `Drums`; `Violin, fiddle` maps to `Violin`. When aliases match, the maximum returned score is used, not the sum. Broad categories remain broad. There is no separate Viola label. No labels are invented from genre tags such as “Drum and bass.”

**“Instrumental” is not a YAMNet label**, and absence of a vocal prediction does not establish the absence of vocals. The app therefore shows `Music`, supported instrument labels, or “No confident detection” instead of fabricating an Instrumental score. Silence is displayed only when the model explicitly returns Silence above threshold. A failed request is marked “Analysis failed,” never silence.

## API

- `GET /health`: local configuration, FFmpeg availability, model, and supported events. “Ready” means configured; it does not assert remote uptime or validate the token.
- `POST /api/analyze`: multipart `file`, optional query parameter `threshold`; returns JSON after processing.
- `POST /api/analyze/stream`: same input; newline-delimited JSON with `progress`, `result`, or `error` messages for the UI. Errors detected after streaming begins are error messages inside an HTTP 200 stream.
- `GET /docs`: interactive FastAPI API documentation.

```bash
curl -X POST 'http://127.0.0.1:8000/api/analyze?threshold=0.30' \
  -F 'file=@/path/to/recording.mp3'
```

Response shape (illustrative scores):

```json
{
  "duration": 10,
  "timeline": [
    {"start": 0, "end": 10, "events": ["Drums", "Piano"],
     "confidences": {"Drums": 0.78, "Piano": 0.91}, "status": "ok"}
  ],
  "windows": [
    {"start": 0, "end": 5, "events": [{"name": "Drums", "confidence": 0.78}, {"name": "Piano", "confidence": 0.91}], "status": "ok", "error": null},
    {"start": 5, "end": 10, "events": [{"name": "Drums", "confidence": 0.78}, {"name": "Piano", "confidence": 0.91}], "status": "ok", "error": null}
  ],
  "instruments": {
    "Drums": [{"start": 0, "end": 10, "average_confidence": 0.78}],
    "Piano": [{"start": 0, "end": 10, "average_confidence": 0.91}]
  },
  "model": "Google YAMNet v1 (AudioSet, 521 labels)",
  "provider": "Hugging Face Space: thelou1s/yamnet",
  "chunk_duration": 5,
  "threshold": 0.3,
  "failed_chunks": 0,
  "warnings": ["Community-hosted YAMNet returns only its top five AudioSet labels per chunk; other sounds may be omitted."]
}
```

The historical `instruments` field includes voices and other supported sounds too. Raw windows retain scores. Merged timeline entries combine only adjacent **identical event sets** with identical status, and confidence is weighted by chunk duration. Instrument tracks merge continuous presence of each event independently. Intervals use `[start, end)` boundaries; the final end is clamped to actual decoded duration. No gap filling or additional smoothing blurs changes between five-second chunks.

## Failure handling and storage

Invalid/empty audio returns 400; too-large files return 413; missing token returns 503; a busy local analyzer returns 429. Remote timeouts, network errors, rate limits and transient errors receive limited retries with backoff. A final chunk failure is retained in a partial result so other chunks can succeed. A fatal remote authentication/configuration error stops further remote calls and marks the remaining intervals failed. Even an all-failed run returns an explicit result with `failed_chunks` and explanations; it is not successful detection.

FFmpeg decodes once to mono 16 kHz PCM16 in a request-scoped temporary directory. Integer PCM corresponds to normalized amplitude in `[-1, 1]`; the remote host converts it to the waveform YAMNet requires. Quiet recordings are not peak-amplified into noise. Decoding is duration-bounded and times out after 120 seconds. Chunk WAV bytes are generated one at a time in memory. The application deletes its upload and decoded files after success, failure, or cancellation and closes FastAPI's upload spool. It has no database or music library.

**Hosted storage is outside this app's control.** Chunks are transmitted to a public community Space that can cache Gradio uploads or log activity. We cannot promise remote deletion. Tokens stay on the Python backend and are never returned in health responses or rendered into the page. This local development server is bound to loopback; add authentication and deployment-specific limits before exposing a shared token publicly.

## Free access limitations

The public Space was callable for free during verification. A Hugging Face account and read token are free. This is **community demonstration access**, not a promised free-tier inference quota: the host has no published guaranteed request allocation, latency, or uptime. It may sleep, disappear, return 429/503, or change its response format. There is no automatic paid fallback or billing integration. Inference Providers credits and ZeroGPU GPU quotas are not the quota system of this CPU Space. See [Spaces API documentation](https://huggingface.co/docs/hub/spaces-api-endpoints).

Creating your own replacement Space may have different plan requirements; [current Spaces documentation](https://huggingface.co/docs/hub/spaces-overview) distinguishes creation eligibility from free CPU hourly compute. This project does not create a Space or provision a paid endpoint.

## Validation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check app/static/app.js  # optional syntax check; Node is not needed to run the app
python -m scripts.verify_hosted  # real authenticated synthetic inference
# Optional, synthetic silence only, no token:
python -m scripts.verify_hosted --public-probe
```

Unit/integration tests use a fake classifier or mocked HTTP transport; they do not spend hosted quota or claim model accuracy. They cover real FFmpeg format conversion, stereo downmix/resampling, chunk timestamps, empty/invalid audio, duration limits, real label mapping, thresholds, merging, retry behavior, malformed responses, token handling, partial failures, progress, and file cleanup. `requirements-lock.txt` records the exact development environment, including test dependencies; use it for reproducible installs on a compatible platform.

Instrument recognition in polyphonic music is difficult. Similar instruments may be confused, soft instruments may be buried, and AudioSet labels are often broad. This application's verification is functional, not an accuracy benchmark. Stem separation is not included: it would need additional hosted infrastructure and does not remove these limitations.

## Layout

```text
app/
  main.py                     FastAPI, health, upload and progress endpoints
  config.py                   Environment configuration
  models/                     Response schemas and full YAMNet label list
  services/
    audio_processing.py       FFmpeg conversion and bounded chunk generation
    hosted_classifier.py      Token-authenticated API adapter and retries
    labels.py                 Verified clean label mapping
    timeline_processor.py     Merged timelines and sound tracks
    analysis.py               Upload lifecycle and analysis orchestration
  static/                     Plain HTML/CSS/JavaScript interface
tests/                        Automated tests; no real API calls
scripts/verify_hosted.py       Optional live synthetic probe
docs/                         Dated hosted-model verification evidence
```
