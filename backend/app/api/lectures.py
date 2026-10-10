from __future__ import annotations

import asyncio
import shutil
import sys
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import PlainTextResponse

from ..models import (
    HealthComponent,
    HealthResponse,
    LectureDetail,
    LectureSummary,
    LectureUpdate,
)
from ..services.exporter import render_markdown
from ..services.media import SUPPORTED_EXTENSIONS
from ..services.whisper import faster_whisper_readiness, whisper_cpp_readiness

router = APIRouter(prefix="/api")


def _install_ffmpeg() -> str:
    if sys.platform == "darwin":
        return "brew install ffmpeg"
    if sys.platform == "win32":
        return "winget install --id Gyan.FFmpeg"
    return "sudo apt-get update && sudo apt-get install -y ffmpeg"


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    processor = request.app.state.processor
    whisper_cpp = whisper_cpp_readiness(settings)
    faster_whisper = faster_whisper_readiness(settings)
    selected_backend = processor.transcription.selected_backend()
    components = {
        "database": HealthComponent(
            ready=settings.database_path.is_file(),
            detail=str(settings.database_path.resolve()),
            remediation="Restart PocketTA so it can initialize its local database.",
        ),
        "storage": HealthComponent(
            ready=settings.pocketta_data_dir.is_dir(),
            detail=str(settings.pocketta_data_dir.resolve()),
            remediation=f"mkdir -p {settings.lectures_dir}",
        ),
        "ffmpeg": HealthComponent(
            ready=settings.executable_available(settings.ffmpeg_path),
            detail=settings.ffmpeg_path,
            remediation=_install_ffmpeg(),
        ),
        "ffprobe": HealthComponent(
            ready=settings.executable_available(settings.ffprobe_path),
            detail=settings.ffprobe_path,
            remediation=_install_ffmpeg(),
        ),
        "whisper_cli": HealthComponent(
            ready=settings.executable_available(settings.whisper_cli_path),
            detail=(
                str(settings.whisper_cli_path)
                if settings.executable_available(settings.whisper_cli_path)
                else f"Missing whisper.cpp CLI at {settings.whisper_cli_path}. Build whisper.cpp, or set WHISPER_CLI_PATH in .env."
            ),
            remediation=(
                "cmake -S vendor/whisper.cpp -B vendor/whisper.cpp/build "
                "-DCMAKE_BUILD_TYPE=Release && "
                "cmake --build vendor/whisper.cpp/build --config Release -j 4"
            ),
        ),
        "whisper_model": HealthComponent(
            ready=settings.whisper_model_path.is_file(),
            detail=(
                str(settings.whisper_model_path)
                if settings.whisper_model_path.is_file()
                else f"Missing whisper.cpp model at {settings.whisper_model_path}. Place ggml-base.en.bin there, or set WHISPER_MODEL_PATH in .env."
            ),
            remediation=(
                "bash vendor/whisper.cpp/models/download-ggml-model.sh base.en"
            ),
        ),
        "whisper_cpp": HealthComponent(
            ready=whisper_cpp.ready,
            detail=whisper_cpp.detail,
        ),
        "faster_whisper": HealthComponent(
            ready=faster_whisper.ready,
            detail=faster_whisper.detail,
        ),
        "transcription_backend": HealthComponent(
            ready=True,
            detail=f"configured={settings.transcription_backend}; selected={selected_backend}",
        ),
    }
    components["document_renderer"] = HealthComponent(
        ready=settings.executable_available(settings.libreoffice_path),
        detail="LibreOffice is required for PPTX previews",
        remediation="Install LibreOffice and set LIBREOFFICE_PATH to its soffice executable.",
    )
    if settings.model_provider == "cerebras":
        components["cerebras"] = HealthComponent(
            ready=bool(settings.cerebras_api_key),
            detail=(
                "Cloud text and vision processing configured"
                if settings.cerebras_api_key
                else "Missing CEREBRAS_API_KEY"
            ),
            remediation="Set CEREBRAS_API_KEY in the server environment.",
        )
        return HealthResponse(ready=components["cerebras"].ready, components=components)
    try:
        models = await processor.lm_studio.available_models()
        configured = settings.lm_studio_model_id
        components["lm_studio"] = HealthComponent(
            ready=bool(configured and configured in models),
            detail=(
                f"model {configured} is available"
                if configured and configured in models
                else f"configure LM_STUDIO_MODEL_ID; available: {', '.join(models) or 'none'}"
            ),
            remediation=(
                "In LM Studio: download Qwen 3.5 4B, load it with a 16K context, "
                "start the server on 127.0.0.1:1234, then copy its ID into "
                "LM_STUDIO_MODEL_ID in .env."
            ),
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        components["lm_studio"] = HealthComponent(
            ready=False,
            detail=f"Local server unavailable: {error}",
            remediation=(
                "Open LM Studio > Developer, load Qwen 3.5 4B, and start the "
                "local server on 127.0.0.1:1234."
            ),
        )
    required_ready = [
        components["database"].ready,
        components["storage"].ready,
        components["ffmpeg"].ready,
        components["ffprobe"].ready,
        components["lm_studio"].ready,
    ]
    if settings.transcription_backend == "faster_whisper":
        required_ready.append(faster_whisper.ready)
    elif settings.transcription_backend == "whisper_cpp":
        required_ready.append(whisper_cpp.ready)
    else:
        required_ready.append(faster_whisper.ready or whisper_cpp.ready)
    return HealthResponse(ready=all(required_ready), components=components)


@router.post(
    "/lectures", response_model=LectureSummary, status_code=status.HTTP_202_ACCEPTED
)
async def upload_lecture(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    course_id: str | None = Form(default=None),
) -> LectureSummary:
    settings = request.app.state.settings
    database = request.app.state.database
    processor = request.app.state.processor
    if course_id and not request.app.state.courses.course(course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    filename = Path(file.filename or "recording").name
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported media type. Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )
    lecture_id = str(uuid.uuid4())
    lecture_dir = settings.lectures_dir / lecture_id
    lecture_dir.mkdir(parents=True, exist_ok=False)
    source_path = lecture_dir / f"source{suffix}"
    max_bytes = settings.max_upload_mb * 1024 * 1024
    written = 0
    try:
        with source_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Upload exceeds the {settings.max_upload_mb} MB limit",
                    )
                output.write(chunk)
        if written == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty")
        clean_title = title.strip() if title and title.strip() else None
        if clean_title and len(clean_title) > 200:
            raise HTTPException(
                status_code=422, detail="Title must be 200 characters or fewer"
            )
        database.create_lecture(lecture_id, filename, source_path, clean_title)
        request.app.state.courses.attach_lecture(lecture_id, course_id)
        processor.enqueue(lecture_id)
        lecture = database.get_lecture(lecture_id)
        assert lecture is not None
        return LectureSummary(
            **lecture.model_dump(exclude={"transcript", "study_pack"})
        )
    except Exception:
        if not database.exists(lecture_id):
            shutil.rmtree(lecture_dir, ignore_errors=True)
        raise
    finally:
        await file.close()


@router.get("/lectures", response_model=list[LectureSummary])
def list_lectures(request: Request) -> list[LectureSummary]:
    return request.app.state.database.list_lectures()


@router.get("/lectures/{lecture_id}", response_model=LectureDetail)
def get_lecture(request: Request, lecture_id: str) -> LectureDetail:
    lecture = request.app.state.database.get_lecture(lecture_id)
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    return lecture


@router.post(
    "/lectures/demo",
    response_model=LectureSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_demo_lecture(
    request: Request, course_id: str | None = None
) -> LectureSummary:
    settings = request.app.state.settings
    if course_id and not request.app.state.courses.course(course_id):
        raise HTTPException(status_code=404, detail="Course not found")
    sample = Path(__file__).resolve().parents[3] / "samples" / "pocketta-demo.m4a"
    if not sample.is_file():
        raise HTTPException(
            status_code=503,
            detail="The bundled demo recording is unavailable; use a local recording instead",
        )
    lecture_id = str(uuid.uuid4())
    lecture_dir = settings.lectures_dir / lecture_id
    lecture_dir.mkdir(parents=True, exist_ok=False)
    source_path = lecture_dir / "source.m4a"
    try:
        await asyncio.to_thread(shutil.copyfile, sample, source_path)
        request.app.state.database.create_lecture(
            lecture_id,
            sample.name,
            source_path,
            "PocketTA computation demo",
        )
        request.app.state.courses.attach_lecture(lecture_id, course_id)
        request.app.state.processor.enqueue(lecture_id)
        lecture = request.app.state.database.get_lecture(lecture_id)
        assert lecture is not None
        return LectureSummary(
            **lecture.model_dump(exclude={"transcript", "study_pack"})
        )
    except Exception:
        if not request.app.state.database.exists(lecture_id):
            shutil.rmtree(lecture_dir, ignore_errors=True)
        raise


@router.patch("/lectures/{lecture_id}", response_model=LectureDetail)
def update_lecture(
    request: Request, lecture_id: str, update: LectureUpdate
) -> LectureDetail:
    database = request.app.state.database
    processor = request.app.state.processor
    lecture = database.get_lecture(lecture_id)
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    if processor.is_processing(lecture_id):
        raise HTTPException(
            status_code=409, detail="Wait for processing to stop before editing"
        )
    if update.title is not None:
        database.update_title(lecture_id, update.title)
    if update.corrections:
        if not lecture.transcript:
            raise HTTPException(
                status_code=409, detail="This lecture has no transcript to edit"
            )
        corrections = {item.segment_id: item.text for item in update.corrections}
        if len(corrections) != len(update.corrections):
            raise HTTPException(
                status_code=422, detail="Duplicate transcript segment correction"
            )
        valid_ids = {segment.id for segment in lecture.transcript.segments}
        unknown = sorted(set(corrections) - valid_ids)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown transcript segment IDs: {', '.join(unknown)}",
            )
        revised = lecture.transcript.model_copy(deep=True)
        for segment in revised.segments:
            if segment.id in corrections:
                segment.text = corrections[segment.id]
        database.replace_transcript_and_invalidate_pack(lecture_id, revised)
        lecture_dir = request.app.state.settings.lectures_dir / lecture_id
        (lecture_dir / "transcript.json").write_text(
            revised.model_dump_json(indent=2), encoding="utf-8"
        )
        (lecture_dir / "study_pack.json").unlink(missing_ok=True)
    refreshed = database.get_lecture(lecture_id)
    assert refreshed is not None
    return refreshed


@router.post(
    "/lectures/{lecture_id}/generate",
    response_model=LectureSummary,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_study_pack(request: Request, lecture_id: str) -> LectureSummary:
    processor = request.app.state.processor
    try:
        processor.enqueue_generation(lecture_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Lecture not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    lecture = request.app.state.database.get_lecture(lecture_id)
    assert lecture is not None
    return LectureSummary(**lecture.model_dump(exclude={"transcript", "study_pack"}))


@router.post("/lectures/{lecture_id}/cancel", response_model=LectureSummary)
async def cancel_lecture(request: Request, lecture_id: str) -> LectureSummary:
    try:
        found = await request.app.state.processor.cancel(lecture_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not found:
        raise HTTPException(status_code=404, detail="Lecture not found")
    lecture = request.app.state.database.get_lecture(lecture_id)
    assert lecture is not None
    return LectureSummary(**lecture.model_dump(exclude={"transcript", "study_pack"}))


@router.get("/lectures/{lecture_id}/export.md", response_class=PlainTextResponse)
def export_lecture(request: Request, lecture_id: str) -> PlainTextResponse:
    lecture = request.app.state.database.get_lecture(lecture_id)
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    try:
        content = render_markdown(lecture, request.app.state.settings.model_provider)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return PlainTextResponse(
        content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="pocketta-{lecture_id}.md"'
        },
    )


@router.delete("/lectures/{lecture_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lecture(request: Request, lecture_id: str) -> None:
    if not await request.app.state.processor.delete(lecture_id):
        raise HTTPException(status_code=404, detail="Lecture not found")
