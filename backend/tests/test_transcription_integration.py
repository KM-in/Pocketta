"""Optional end-to-end check for uploaded audio and the real local Whisper runtime."""

from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import Concept, Flashcard, Note, QuizQuestion, StudyPack
from backend.app.services.whisper import faster_whisper_readiness, whisper_cpp_readiness

FIXTURE = Path(__file__).parent / "fixtures" / "transcription" / "lecture.mp4"


def _local_whisper_settings() -> tuple[Settings | None, str]:
    configured = Settings()
    cli = Path(
        os.getenv("POCKETTA_TEST_WHISPER_CLI") or str(configured.whisper_cli_path)
    )
    if not configured.executable_available(cli):
        cli = Path(shutil.which("whisper-cli") or "")
    model = Path(
        os.getenv("POCKETTA_TEST_WHISPER_MODEL") or str(configured.whisper_model_path)
    )
    if not cli or not configured.executable_available(cli):
        return None, "Install whisper.cpp or set WHISPER_CLI_PATH"
    if not model.is_file():
        return None, "Set POCKETTA_TEST_WHISPER_MODEL to a prepared local Whisper model"
    settings = Settings(
        _env_file=None,
        whisper_cli_path=cli,
        whisper_model_path=model,
        transcription_backend="whisper_cpp",
    )
    readiness = whisper_cpp_readiness(settings)
    if not readiness.ready:
        return None, readiness.detail
    return settings, ""


@pytest.mark.parametrize("backend", ["whisper_cpp", "faster_whisper"])
def test_uploaded_recording_is_transcribed_by_local_whisper(
    tmp_path: Path, backend: str
) -> None:
    if backend == "faster_whisper":
        configured = Settings()
        settings = Settings(
            _env_file=None,
            transcription_backend="faster_whisper",
            faster_whisper_model_path=os.getenv("POCKETTA_TEST_FASTER_WHISPER_MODEL")
            or configured.faster_whisper_model_path,
            faster_whisper_model_name=os.getenv(
                "POCKETTA_TEST_FASTER_WHISPER_MODEL_NAME"
            )
            or configured.faster_whisper_model_name,
            faster_whisper_compute_type=os.getenv(
                "POCKETTA_TEST_FASTER_WHISPER_COMPUTE_TYPE"
            )
            or configured.faster_whisper_compute_type,
            ffmpeg_path=configured.ffmpeg_path,
            ffprobe_path=configured.ffprobe_path,
        )
        readiness = faster_whisper_readiness(settings)
        if not readiness.ready:
            pytest.skip(readiness.detail)
        reason = ""
    else:
        settings, reason = _local_whisper_settings()
    if settings is None:
        pytest.skip(reason)
    if not shutil.which(settings.ffmpeg_path) or not shutil.which(
        settings.ffprobe_path
    ):
        pytest.skip("FFmpeg and FFprobe are required for recording normalization")
    assert FIXTURE.is_file(), "the short synthetic speech fixture must be checked in"

    settings = settings.model_copy(
        update={
            "pocketta_data_dir": tmp_path,
            # Keep confidence handling deterministic for a synthetic speech fixture.
            "uncertain_confidence_threshold": 0.0,
        }
    )
    app = create_app(settings)

    async def skip_indexing(_source_id: str) -> None:
        return None

    async def local_study_pack(transcript, *, source_id=None) -> StudyPack:
        del source_id
        segment_id = transcript.segments[0].id
        return StudyPack(
            title="Local transcription integration fixture",
            overview="Generated from the real local transcript.",
            notes=[
                Note(
                    title="Transcript",
                    body=transcript.segments[0].text,
                    segment_ids=[segment_id],
                )
            ],
            concepts=[
                Concept(
                    name="Transcript evidence",
                    definition=transcript.segments[0].text,
                    segment_ids=[segment_id],
                )
            ],
            flashcards=[
                Flashcard(
                    front="What does the transcript say?",
                    back=transcript.segments[0].text,
                    segment_ids=[segment_id],
                )
            ],
            quiz=[
                QuizQuestion(
                    question="Which source was transcribed?",
                    options=["The lecture", "No source"],
                    correct_answer=0,
                    explanation="The uploaded lecture was transcribed.",
                    segment_ids=[segment_id],
                )
            ],
        )

    # Keep the integration local: test the actual upload, FFmpeg normalization,
    # local Whisper decoding, persistence, and API readback without calling a model API.
    app.state.processor.knowledge.index_source = skip_indexing
    app.state.processor.lm_studio.generate = local_study_pack

    with TestClient(app) as client:
        uploaded = client.post(
            "/api/lectures",
            files={"file": ("lecture.mp4", FIXTURE.read_bytes(), "video/mp4")},
            data={"title": "Local Whisper integration fixture"},
        )
        assert uploaded.status_code == 202, uploaded.text
        lecture_id = uploaded.json()["id"]

        deadline = time.monotonic() + 90
        detail = None
        while time.monotonic() < deadline:
            response = client.get(f"/api/lectures/{lecture_id}")
            assert response.status_code == 200, response.text
            detail = response.json()
            if detail["transcript"] is not None:
                break
            if detail["status"] == "failed":
                pytest.fail(f"uploaded recording processing failed: {detail['error']}")
            time.sleep(0.2)

        assert detail is not None and detail["transcript"] is not None, (
            "recording did not produce a persisted transcript before timeout"
        )
        assert detail["status"] == "completed"
        transcript = detail["transcript"]
        assert transcript["duration_ms"] > 0
        assert transcript["segments"]
        recognized = " ".join(segment["text"] for segment in transcript["segments"])
        normalized = re.sub(r"[^a-z0-9]+", " ", recognized.lower())
        for word in ("process", "program", "stack", "register"):
            assert word in normalized, (
                f"Whisper transcript omitted {word!r}: {recognized!r}"
            )

        lecture_dir = settings.lectures_dir / lecture_id
        assert (lecture_dir / "transcript.json").is_file()
        assert not (lecture_dir / "audio.wav").exists()
