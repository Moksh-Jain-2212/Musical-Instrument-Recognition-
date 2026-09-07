from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent
SPACE_ID = "thelou1s/yamnet"
SPACE_URL = "https://thelou1s-yamnet.hf.space"
MODEL_NAME = "Google YAMNet v1 (AudioSet, 521 labels)"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")
    hf_token: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    instrument_provider: Literal["yamnet", "gemini"] = "yamnet"
    gemini_model: str = Field("gemini-2.5-flash", pattern=r"^gemini-[a-zA-Z0-9.\-]+$")
    chunk_duration: float = Field(5, ge=3, le=10)
    confidence_threshold: float = Field(0.20, ge=0.05, le=0.80)
    instrument_fallback_enabled: bool = False
    api_timeout_seconds: float = Field(45, ge=1, le=180)
    api_retries: int = Field(2, ge=0, le=3)
    max_upload_mb: int = Field(100, ge=1, le=500)
    max_duration_seconds: int = Field(900, ge=1, le=3600)
    ffmpeg_path: str = ""

    @property
    def credential_name(self) -> str:
        return "GEMINI_API_KEY" if self.instrument_provider == "gemini" else "HF_TOKEN"

    @property
    def credential_configured(self) -> bool:
        key = self.gemini_api_key if self.instrument_provider == "gemini" else self.hf_token
        return bool(key.get_secret_value().strip())

    @property
    def model_name(self) -> str:
        return self.gemini_model if self.instrument_provider == "gemini" else MODEL_NAME
