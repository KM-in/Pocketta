from __future__ import annotations
import asyncio
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field, field_validator
from .lectures import upload_lecture

router = APIRouter(prefix="/api")


class CourseInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)

    @field_validator("title")
    @classmethod
    def clean(cls, value):
        if not value.strip():
            raise ValueError("Title must not be blank")
        return value.strip()


def require_course(request, id):
    course = request.app.state.courses.course(id)
    if not course:
        raise HTTPException(404, "Course not found")
    return course


def require_source(request, id):
    source = request.app.state.courses.source(id)
    if not source:
        raise HTTPException(404, "Source not found")
    return source


def public_source(source):
    source = dict(source)
    source["content_units"] = [
        {k: v for k, v in u.items() if k not in ("image_path", "vision_json")}
        | {
            "preview_url": (
                f'/sources/{source["id"]}/units/{u["id"]}/image'
                if u["image_path"]
                else None
            )
        }
        for u in source["content_units"]
    ]
    source["asset_url"] = f'/sources/{source["id"]}/asset'
    return source


@router.get("/courses")
def courses(request: Request):
    return request.app.state.courses.courses()


@router.post("/courses", status_code=201)
def create_course(request: Request, payload: CourseInput):
    return request.app.state.courses.create_course(payload.title, payload.description)


@router.get("/courses/{id}")
def course_detail(request: Request, id: str):
    return require_course(request, id)


@router.patch("/courses/{id}")
def edit_course(request: Request, id: str, payload: CourseInput):
    require_course(request, id)
    with request.app.state.database._connect() as c:
        c.execute(
            "UPDATE courses SET title=?,description=? WHERE id=?",
            (payload.title, payload.description, id),
        )
    return require_course(request, id)


@router.delete("/courses/{id}", status_code=204)
def delete_course(request: Request, id: str):
    require_course(request, id)
    with request.app.state.database._connect() as c:
        if c.execute("SELECT 1 FROM sources WHERE course_id=?", (id,)).fetchone():
            raise HTTPException(
                409, "Delete the course sources before deleting this course"
            )
        c.execute("DELETE FROM courses WHERE id=?", (id,))


@router.get("/courses/{id}/sources")
def list_sources(request: Request, id: str):
    require_course(request, id)
    return request.app.state.courses.summaries(id)


@router.post("/courses/{id}/sources", status_code=202)
async def upload_source(
    request: Request,
    id: str,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
):
    require_course(request, id)
    name = Path(file.filename or "source").name
    suffix = Path(name).suffix.lower()
    if suffix not in (".pdf", ".pptx"):
        lecture = await upload_lecture(request, file, title, id)
        return public_source(require_source(request, lecture.id))
    if title is not None and (not title.strip() or len(title.strip()) > 200):
        await file.close()
        raise HTTPException(422, "Title must contain 1–200 characters")
    source_id = str(uuid.uuid4())
    directory = (
        request.app.state.settings.pocketta_data_dir.resolve() / "sources" / source_id
    )
    directory.mkdir(parents=True)
    path = directory / f"source{suffix}"
    try:
        size = 0
        with path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > request.app.state.settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(
                        413, "Upload exceeds configured file size limit"
                    )
                output.write(chunk)
        if not size:
            raise HTTPException(400, "The uploaded file is empty")
        with request.app.state.database._connect() as c:
            c.execute(
                "INSERT INTO sources(id,course_id,name,type,file_path,status,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    source_id,
                    id,
                    title.strip() if title else name,
                    suffix[1:],
                    str(path),
                    "queued",
                    datetime.now(UTC).isoformat(),
                ),
            )
        request.app.state.documents.enqueue(source_id)
        return public_source(require_source(request, source_id))
    except Exception:
        if not request.app.state.courses.source(source_id):
            shutil.rmtree(directory, ignore_errors=True)
        raise
    finally:
        await file.close()


@router.get("/sources/{id}")
def source_detail(request: Request, id: str):
    return public_source(require_source(request, id))


@router.get("/sources/{id}/status")
def source_status(request: Request, id: str):
    source = require_source(request, id)
    return {k: source[k] for k in ("id", "status", "progress", "error")}


@router.post("/sources/{id}/{action}", status_code=202)
async def source_action(request: Request, id: str, action: str):
    source = require_source(request, id)
    if action not in ("retry", "cancel", "generate"):
        raise HTTPException(404, "Unknown source action")
    try:
        if source["type"] == "recording":
            processor = request.app.state.processor
            if action == "cancel":
                await processor.cancel(id)
            elif (
                action == "generate"
                or request.app.state.database.get_lecture(id).transcript
            ):
                processor.enqueue_generation(id)
            else:
                if processor.is_processing(id):
                    raise ValueError("Source is already processing")
                request.app.state.database.update_status(id, "queued")
                processor.enqueue(id)
        else:
            processor = request.app.state.documents
            if action == "cancel":
                if id not in processor.pending and id not in processor.active:
                    raise ValueError("Source is not processing")
                await processor.cancel(id)
            else:
                if action == "generate" and not source["content_units"]:
                    raise ValueError("Extract source content first")
                processor.enqueue(id, generation_only=action == "generate")
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return public_source(require_source(request, id))


@router.delete("/sources/{id}", status_code=204)
async def delete_source(request: Request, id: str):
    source = require_source(request, id)
    if source["type"] == "recording":
        await request.app.state.processor.delete(id)
    else:
        await request.app.state.documents.cancel(id)
        directory = Path(request.app.state.courses.path(id)).parent
        await asyncio.to_thread(shutil.rmtree, directory)
        with request.app.state.database._connect() as c:
            c.execute("DELETE FROM model_runs WHERE source_id=?", (id,))
            c.execute("DELETE FROM sources WHERE id=?", (id,))


@router.get("/sources/{id}/asset")
def asset(request: Request, id: str):
    source = require_source(request, id)
    path = Path(request.app.state.courses.path(id))
    if source["type"] == "pptx":
        path = path.with_suffix(".pdf")
    if not path.is_file():
        raise HTTPException(404, "Source preview is not available yet")
    return FileResponse(
        path,
        media_type="application/pdf" if source["type"] in ("pdf", "pptx") else None,
    )


@router.get("/sources/{id}/units/{unit_id}/image")
def image(request: Request, id: str, unit_id: str):
    source = require_source(request, id)
    unit = next((u for u in source["content_units"] if u["id"] == unit_id), None)
    if not unit or not unit["image_path"] or not Path(unit["image_path"]).is_file():
        raise HTTPException(404, "Preview not found")
    return FileResponse(unit["image_path"], media_type="image/png")


@router.get("/citations/{unit_id}")
def citation(request: Request, unit_id: str):
    with request.app.state.database._connect() as c:
        row = c.execute(
            "SELECT source_id FROM content_units WHERE id=?", (unit_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Citation not found")
    source = require_source(request, row["source_id"])
    unit = next(u for u in source["content_units"] if u["id"] == unit_id)
    kind, location = unit["location"].split(":", 1)
    result = {
        "content_unit_id": unit_id,
        "source_id": source["id"],
        "course_id": source["course_id"],
        "source_name": source["name"],
        "excerpt": unit["text"],
        "uncertain": bool(unit["uncertain"]),
    }
    if kind == "time":
        start, end = location.split(":")[0].split("-")
        result.update(start_sec=int(start) / 1000, end_sec=int(end) / 1000)
    else:
        result[f"{kind}_no"] = int(location)
    return result


@router.get("/sources/{id}/export.md", response_class=PlainTextResponse)
def export(request: Request, id: str):
    source = require_source(request, id)
    pack = source["study_pack"]
    if not pack:
        raise HTTPException(409, "Generate a study pack first")
    units = {u["id"]: u for u in source["content_units"]}
    lines = [f'# {source["name"]}', "", pack["overview"], ""]
    for key in ("notes", "concepts", "flashcards", "quiz"):
        lines.extend([f"## {key.title()}", ""])
        for item in pack[key]:
            for field in (
                "title",
                "name",
                "question",
                "front",
                "body",
                "definition",
                "back",
                "explanation",
            ):
                if field in item:
                    lines.extend([item[field], ""])
            if "options" in item:
                lines.extend(
                    f"- {option}"
                    + (" (correct)" if i == item["correct_answer"] else "")
                    for i, option in enumerate(item["options"])
                )
            lines.extend(
                [
                    "Evidence: "
                    + ", ".join(
                        f'[{source["name"]} · {units[u]["location"]}](#{u})'
                        for u in item["content_unit_ids"]
                    ),
                    "",
                ]
            )
    for unit in units.values():
        lines.extend(
            [f'<a id="{unit["id"]}"></a>', f'### {unit["location"]}', unit["text"], ""]
        )
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="pocketta-{id}.md"'},
    )
