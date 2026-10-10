from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    model_provider: Literal["lm_studio", "cerebras"] = "lm_studio"
    cerebras_api_key: str = ""
    cerebras_text_model: str = "qwen-3.8-27b"
    cerebras_vision_model: str = "qwen-3.8-27b"
    libreoffice_path: str = "soffice"
    max_document_pages: int = 500

    pocketta_data_dir: Path = Path("./data")
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    whisper_cli_path: Path = Path("./vendor/whisper.cpp/build/bin/whisper-cli")
    whisper_model_path: Path = Path("./vendor/whisper.cpp/models/ggml-base.en.bin")
    whisper_use_gpu: bool = False
    transcription_backend: Literal["auto", "whisper_cpp", "faster_whisper"] = "auto"
    faster_whisper_model_path: Path | None = None
    faster_whisper_model_name: str = "turbo"
    faster_whisper_compute_type: str = "float16"
    faster_whisper_beam_size: int = 5
    faster_whisper_batch_size: int = 8
    faster_whisper_vad_filter: bool = False
    lm_studio_base_url: str = "http://127.0.0.1:1234/v1"
    lm_studio_model_id: str = ""
    lm_studio_api_key: str = ""
    lm_studio_timeout_seconds: float = 480.0
    lm_studio_chunk_chars: int = 14_000
    lm_studio_chunk_overlap_segments: int = 1
    max_upload_mb: int = 200
    uncertain_confidence_threshold: float = 0.60
    temporary_file_max_age_hours: int = 24

    @field_validator("lm_studio_chunk_chars")
    @classmethod
    def chunk_size_must_be_practical(cls, value: int) -> int:
        if value < 2_000:
            raise ValueError("LM Studio chunk size must be at least 2000 characters")
        return value

    @field_validator("faster_whisper_model_path", mode="before")
    @classmethod
    def empty_faster_whisper_path_is_none(cls, value: object) -> object:
        if value == "":
            return None
        return value

    @field_validator("lm_studio_base_url")
    @classmethod
    def lm_studio_must_be_loopback(cls, value: str) -> str:
        host = urlparse(value).hostname
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("LM Studio must use a loopback URL")
        return value.rstrip("/")

    @property
    def database_path(self) -> Path:
        return self.pocketta_data_dir / "pocketta.sqlite3"

    @property
    def lectures_dir(self) -> Path:
        return self.pocketta_data_dir / "lectures"

    def prepare_directories(self) -> None:
        self.lectures_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def executable_available(value: str | Path) -> bool:
        candidate = str(value)
        if os.path.sep in candidate or (os.path.altsep and os.path.altsep in candidate):
            return Path(candidate).expanduser().is_file()
        return shutil.which(candidate) is not None
