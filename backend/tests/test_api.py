from pathlib import Path
from unittest.mock import AsyncMock, Mock

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.models import LectureStatus
from backend.app.services.whisper import Readiness
from backend.tests.test_models import study_pack, transcript


async def _available_models():
    return ["local-qwen"]


def test_upload_rejects_unsupported_extension(tmp_path: Path) -> None:
    app = create_app(Settings(pocketta_data_dir=tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/lectures", files={"file": ("notes.txt", b"not media", "text/plain")}
        )
    assert response.status_code == 415


def test_empty_upload_leaves_no_lecture(tmp_path: Path) -> None:
    app = create_app(Settings(pocketta_data_dir=tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/lectures", files={"file": ("empty.mp3", b"", "audio/mpeg")}
        )
        assert response.status_code == 400
        assert client.get("/api/lectures").json() == []


def test_oversized_upload_cleans_partial_directory(tmp_path: Path) -> None:
    app = create_app(Settings(pocketta_data_dir=tmp_path, max_upload_mb=0))
    with TestClient(app) as client:
        response = client.post(
            "/api/lectures", files={"file": ("large.mp3", b"x", "audio/mpeg")}
        )
        assert response.status_code == 413
        assert client.get("/api/lectures").json() == []
        assert list((tmp_path / "lectures").iterdir()) == []


def test_health_reports_faster_whisper_without_requiring_it_in_auto(
    tmp_path: Path, monkeypatch
) -> None:
    whisper_cli = tmp_path / "whisper-cli"
    whisper_model = tmp_path / "ggml-base.en.bin"
    whisper_cli.write_text("stub", encoding="utf-8")
    whisper_model.write_text("stub", encoding="utf-8")
    monkeypatch.setattr(
        "backend.app.services.whisper.faster_whisper_readiness",
        lambda settings: Readiness(False, "optional CUDA path is not ready"),
    )
    monkeypatch.setattr(
        "backend.app.api.lectures.faster_whisper_readiness",
        lambda settings: Readiness(False, "optional CUDA path is not ready"),
    )
    monkeypatch.setattr(
        "backend.app.services.gateway.ModelGateway.available_models",
        lambda self: _available_models(),
    )
    app = create_app(
        Settings(
            _env_file=None,
            pocketta_data_dir=tmp_path,
            whisper_cli_path=whisper_cli,
            whisper_model_path=whisper_model,
            lm_studio_model_id="local-qwen",
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert body["components"]["faster_whisper"]["ready"] is False
    assert "selected=whisper_cpp" in body["components"]["transcription_backend"]["detail"]


def test_health_failure_has_actionable_remediation(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            pocketta_data_dir=tmp_path,
            ffmpeg_path="missing-pocketta-ffmpeg",
            ffprobe_path="missing-pocketta-ffprobe",
            lm_studio_model_id="missing-model",
        )
    )
    app.state.processor.lm_studio.available_models = AsyncMock(return_value=[])
    with TestClient(app) as client:
        payload = client.get("/api/health").json()
    assert payload["ready"] is False
    assert payload["components"]["ffmpeg"]["remediation"]
    assert "LM Studio" in payload["components"]["lm_studio"]["remediation"]


def test_delete_removes_database_files_and_api_access(tmp_path: Path) -> None:
    app = create_app(Settings(pocketta_data_dir=tmp_path))
    with TestClient(app) as client:
        lecture_id = "delete-me"
        lecture_dir = tmp_path / "lectures" / lecture_id
        lecture_dir.mkdir()
        source = lecture_dir / "source.mp3"
        source.write_bytes(b"local recording")
        app.state.database.create_lecture(lecture_id, "source.mp3", source)

        response = client.delete(f"/api/lectures/{lecture_id}")
        assert response.status_code == 204
        assert not lecture_dir.exists()
        assert client.get(f"/api/lectures/{lecture_id}").status_code == 404
        assert client.get(f"/api/lectures/{lecture_id}/export.md").status_code == 404
        assert client.get("/api/lectures").json() == []


def test_editing_transcript_invalidates_study_pack(tmp_path: Path) -> None:
    app = create_app(Settings(pocketta_data_dir=tmp_path))
    with TestClient(app) as client:
        lecture_id = "editable"
        lecture_dir = tmp_path / "lectures" / lecture_id
        lecture_dir.mkdir()
        source = lecture_dir / "source.mp3"
        source.write_bytes(b"local")
        app.state.database.create_lecture(lecture_id, "source.mp3", source, "Old title")
        app.state.database.save_transcript(lecture_id, transcript())
        app.state.database.save_study_pack(lecture_id, study_pack())
        app.state.database.update_status(lecture_id, LectureStatus.COMPLETED)

        response = client.patch(
            f"/api/lectures/{lecture_id}",
            json={
                "title": "Corrected title",
                "corrections": [
                    {"segment_id": "seg-0001", "text": "Corrected evidence"}
                ],
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["title"] == "Corrected title"
        assert payload["transcript"]["segments"][0]["text"] == "Corrected evidence"
        assert payload["study_pack"] is None
        assert payload["status"] == "transcribed"


def test_generation_retry_uses_saved_transcript(tmp_path: Path) -> None:
    app = create_app(Settings(pocketta_data_dir=tmp_path))
    with TestClient(app) as client:
        lecture_id = "retry"
        lecture_dir = tmp_path / "lectures" / lecture_id
        lecture_dir.mkdir()
        source = lecture_dir / "source.mp3"
        source.write_bytes(b"local")
        app.state.database.create_lecture(lecture_id, "source.mp3", source)
        app.state.database.save_transcript(lecture_id, transcript())
        app.state.database.update_status(lecture_id, LectureStatus.FAILED, "LM unavailable")
        app.state.processor.enqueue_generation = Mock()

        response = client.post(f"/api/lectures/{lecture_id}/generate")
        assert response.status_code == 202
        app.state.processor.enqueue_generation.assert_called_once_with(lecture_id)


def test_demo_endpoint_uses_bundled_attributed_sample(tmp_path: Path) -> None:
    app = create_app(Settings(pocketta_data_dir=tmp_path))
    with TestClient(app) as client:
        app.state.processor.enqueue = Mock()
        response = client.post("/api/lectures/demo")
        assert response.status_code == 202
        payload = response.json()
        assert payload["title"] == "PocketTA computation demo"
        source = tmp_path / "lectures" / payload["id"] / "source.m4a"
        assert source.is_file()
        app.state.processor.enqueue.assert_called_once_with(payload["id"])
