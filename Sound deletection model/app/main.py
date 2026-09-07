import asyncio
import json
from contextlib import aclosing, asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings
from app.models.schemas import AnalysisResult
from app.services.analysis import UploadTooLarge, analyze_upload
from app.services.audio_processing import AudioError, ffmpeg_executable
from app.services.hosted_classifier import HostedClassifier
from app.services.gemini_classifier import GeminiInstrumentClassifier
from app.services.labels import GEMINI_INSTRUMENTS, SUPPORTED_INSTRUMENTS
from app.services.yamnet_classifier import YAMNetInstrumentClassifier

STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, classifier=None, instrument_classifier=None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient(follow_redirects=False) as client:
            app.state.classifier = instrument_classifier or (
                GeminiInstrumentClassifier(config, client) if config.instrument_provider == "gemini"
                else YAMNetInstrumentClassifier(config, classifier or HostedClassifier(config, client)))
            app.state.busy = asyncio.Lock()
            yield

    app = FastAPI(title="Musical Instrument Detector", lifespan=lifespan)

    @app.middleware("http")
    async def upload_limit(request: Request, call_next):
        if request.method == "POST":
            length = request.headers.get("content-length")
            try:
                if length and int(length) > config.max_upload_mb * 1024 * 1024 + 65536:
                    return JSONResponse({"detail": f"File exceeds the {config.max_upload_mb} MB limit."}, status_code=413)
            except ValueError:
                return JSONResponse({"detail": "Invalid Content-Length."}, status_code=400)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/health")
    async def health():
        try:
            ffmpeg_executable(config)
            ffmpeg = True
        except AudioError:
            ffmpeg = False
        token = config.credential_configured
        return {"status": "ready" if token and ffmpeg else "configuration_required",
                "token_configured": token, "ffmpeg_available": ffmpeg,
                "provider": config.instrument_provider, "model": config.model_name, "hosted_availability": "not_checked",
                "required_credential": config.credential_name,
                "chunk_duration": config.chunk_duration if config.instrument_provider == "yamnet" else None,
                "confidence_threshold": config.confidence_threshold,
                "max_upload_mb": config.max_upload_mb, "max_duration_seconds": config.max_duration_seconds,
                "supported_instruments": list(GEMINI_INSTRUMENTS if config.instrument_provider == "gemini" else SUPPORTED_INSTRUMENTS)}

    async def prepare(file: UploadFile):
        if not config.credential_configured:
            await file.close()
            raise HTTPException(503, f"Set {config.credential_name} in .env and restart the server. See README.md for key setup.")
        if app.state.busy.locked():
            await file.close()
            raise HTTPException(429, "Another analysis is running. Please wait until it finishes.")
        # No await between the busy check and lock acquisition.
        await app.state.busy.acquire()

    async def events(file: UploadFile, threshold: float):
        try:
            async with aclosing(analyze_upload(file, config, app.state.classifier, threshold)) as analysis:
                async for event in analysis:
                    yield event
        finally:
            try:
                await file.close()
            finally:
                app.state.busy.release()

    @app.post("/api/analyze", response_model=AnalysisResult)
    async def analyze(file: UploadFile = File(...), threshold: float | None = Query(None, ge=0.01, le=1)):
        await prepare(file)
        try:
            async for event in events(file, threshold if threshold is not None else config.confidence_threshold):
                if event["type"] == "result":
                    result = event["result"]
            return result
        except UploadTooLarge as exc:
            raise HTTPException(413, str(exc)) from exc
        except AudioError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/analyze/stream")
    async def analyze_stream(file: UploadFile = File(...), threshold: float | None = Query(None, ge=0.01, le=1)):
        await prepare(file)

        async def stream():
            try:
                async with aclosing(events(file, threshold if threshold is not None else config.confidence_threshold)) as analysis:
                    async for event in analysis:
                        yield json.dumps(event) + "\n"
            except AudioError as exc:
                yield json.dumps({"type": "error", "message": str(exc)}) + "\n"

        return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
