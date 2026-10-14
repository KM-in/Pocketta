from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    model_provider: Literal["lm_studio", "cerebras"] = "lm_studio"
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    cerebras_api_key: str = ""
    cerebras_completion_token_field: Literal["max_tokens", "max_completion_tokens"] = (
        "max_completion_tokens"
    )
    cerebras_reasoning_effort: Literal["", "none", "low", "medium", "high"] = "medium"
    cerebras_text_model: str = "qwen-3.8-27b"
    cerebras_vision_model: str = "qwen-3.8-27b"
    openai_api_key: str = ""
    openai_embedding_model: str = "text-embedding-3-small"
    # Local inference is the default so merely setting an API key never incurs embedding charges.
    embedding_provider: Literal["api", "fastembed"] = "fastembed"
    fastembed_model: str = "BAAI/bge-small-en-v1.5"
    fastembed_min_similarity: float = Field(default=0.80, ge=0, le=1)
    fastembed_cache_dir: Path | None = None
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str | None = None
    embedding_model: str | None = None
    retrieval_context_chars: int = Field(default=24_000, ge=2000, le=100_000)

    @property
    def effective_embedding_model(self):
        if self.embedding_provider == "fastembed":
            return self.fastembed_model
        return self.embedding_model or self.openai_embedding_model

    @property
    def effective_embedding_key(self):
        return (
            self.openai_api_key
            if self.embedding_api_key is None
            else self.embedding_api_key
        )

    @property
    def embedding_is_local(self):
        return urlparse(self.embedding_base_url).hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }

    @property
    def embedding_enabled(self):
        if self.embedding_provider == "fastembed":
            return True
        return bool(self.effective_embedding_key) or self.embedding_is_local

    @property
    def embedding_identity(self):
        if self.embedding_provider == "fastembed":
            return f"fastembed|{self.fastembed_model}"
        model = self.effective_embedding_model
        return (
            model
            if self.embedding_base_url == "https://api.openai.com/v1"
            else f"{self.embedding_base_url}|{model}"
        )

    @property
    def fastembed_cache_path(self) -> Path:
        return self.fastembed_cache_dir or (self.pocketta_data_dir / "fastembed")

    retrieval_chunk_chars: int = Field(default=1200, ge=200, le=6000)
    retrieval_chunk_overlap_chars: int = Field(default=160, ge=0)
    embedding_batch_size: int = Field(default=32, ge=1, le=128)
    retrieval_min_similarity: float = Field(default=0.65, ge=0, le=1)
    knowledge_infer_topics: bool = False
    verifier_model: str = ""
    grader_model: str = ""
    generation_timeout_seconds: float = Field(default=480, gt=0)
    generation_chunk_chars: int = Field(default=14_000, ge=2000)
    generation_chunk_overlap_segments: int = Field(default=1, ge=0)
    job_concurrency: int = Field(default=2, ge=1)
    course_job_concurrency: int = Field(default=1, ge=1)
    provider_concurrency: int = Field(default=1, ge=1)
    provider_request_interval_seconds: float = Field(default=0, ge=0)
    # provider/model -> input/output USD per million tokens. Unknown rates stay null.
    model_token_rates: dict[str, dict[str, float]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def neutral_generation_settings(self):
        if self.retrieval_chunk_overlap_chars >= self.retrieval_chunk_chars:
            raise ValueError("Retrieval overlap must be smaller than chunk size")
        for neutral, legacy in (
            ("generation_timeout_seconds", "lm_studio_timeout_seconds"),
            ("generation_chunk_chars", "lm_studio_chunk_chars"),
            ("generation_chunk_overlap_segments", "lm_studio_chunk_overlap_segments"),
        ):
            if neutral not in self.model_fields_set:
                setattr(self, neutral, getattr(self, legacy))
        return self

    @field_validator("model_token_rates")
    @classmethod
    def nonnegative_rates(cls, rates):
        import math

        if any(
            not math.isfinite(v) or v < 0
            for rate in rates.values()
            for v in rate.values()
        ):
            raise ValueError("Token rates must be finite and nonnegative")
        return rates

    @property
    def text_model(self):
        return (
            self.cerebras_text_model
            if self.model_provider == "cerebras"
            else self.lm_studio_model_id
        )

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
    lm_studio_timeout_seconds: float = Field(default=480, gt=0)
    lm_studio_chunk_chars: int = 14_000
    lm_studio_chunk_overlap_segments: int = Field(default=1, ge=0)
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

    @field_validator("cerebras_base_url", "embedding_base_url")
    @classmethod
    def cloud_base_url_must_be_http(cls, value: str) -> str:
        value = value.strip()
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "Cloud base URL must be an HTTP(S) URL without credentials, query, or fragment"
            )
        return value.rstrip("/")

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
