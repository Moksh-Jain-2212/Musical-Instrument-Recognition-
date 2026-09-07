from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
SPACE_ID = "thelou1s/yamnet"
SPACE_URL = "https://thelou1s-yamnet.hf.space"
MODEL_NAME = "Google YAMNet v1 (AudioSet, 521 labels)"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    hf_token: SecretStr = SecretStr("")
    chunk_duration: float = Field(5, ge=3, le=10)
    confidence_threshold: float = Field(0.30, ge=0.01, le=1)
    api_timeout_seconds: float = Field(45, ge=1, le=180)
    api_retries: int = Field(2, ge=0, le=3)
    max_upload_mb: int = Field(100, ge=1, le=500)
    max_duration_seconds: int = Field(900, ge=1, le=3600)
    ffmpeg_path: str = ""
