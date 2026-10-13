import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..services.course_packs import CourseStudyPack
from ..services.generation import GenerationError
from .courses import require_course

router = APIRouter(prefix="/api/courses/{course_id}/study-packs")


class PackInput(BaseModel):
    source_ids: list[str] = Field(min_length=1)


@router.post("", status_code=202, response_model=CourseStudyPack)
async def create(request: Request, course_id: str, payload: PackInput):
    require_course(request, course_id)
    try:
        return request.app.state.course_packs.create(course_id, payload.source_ids)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("", response_model=list[CourseStudyPack])
def list_packs(request: Request, course_id: str):
    require_course(request, course_id)
    return request.app.state.course_packs.list(course_id)


@router.get("/{pack_id}", response_model=CourseStudyPack)
def get(request: Request, course_id: str, pack_id: str):
    require_course(request, course_id)
    try:
        return request.app.state.course_packs.get(course_id, pack_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@router.post("/{pack_id}/quiz/retry", status_code=202)
async def retry_quiz(request: Request, course_id: str, pack_id: str):
    require_course(request, course_id)
    try:
        pack = request.app.state.course_packs.check(course_id, pack_id)
        if pack["status"] != "completed":
            raise ValueError(
                "Wait for the course pack to complete before retrying its quiz"
            )
        snapshots = json.loads(pack["snapshots_json"])
        topics = []
        with request.app.state.database._connect() as c:
            topics = [
                r[0]
                for r in c.execute(
                    "SELECT DISTINCT title FROM course_pack_sections WHERE pack_id=? ORDER BY title",
                    (pack_id,),
                )
            ]
        with request.app.state.database._connect() as c:
            c.execute(
                "UPDATE course_packs SET quiz_status='generating' WHERE id=?",
                (pack_id,),
            )
        quiz = await request.app.state.quizzes.generate(
            course_id,
            [s["id"] for s in snapshots if s["has_reliable_material"]],
            pack_id=pack_id,
            fixed_topics=topics or None,
        )
        with request.app.state.database._connect() as c:
            c.execute(
                "UPDATE course_packs SET quiz_id=?,quiz_status='ready',updated_at=datetime('now') WHERE id=?",
                (quiz["id"], pack_id),
            )
        return request.app.state.course_packs.get(course_id, pack_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        with request.app.state.database._connect() as c:
            c.execute(
                "UPDATE course_packs SET quiz_status='failed' WHERE id=?", (pack_id,)
            )
        raise HTTPException(409, str(error)) from error
    except GenerationError as error:
        with request.app.state.database._connect() as c:
            c.execute(
                "UPDATE course_packs SET quiz_status='failed' WHERE id=?", (pack_id,)
            )
        raise HTTPException(
            503, "Mixed quiz generation failed; the course pack remains available"
        ) from error


@router.post("/{pack_id}/import-quizzes", status_code=201)
def import_quizzes(request: Request, course_id: str, pack_id: str):
    require_course(request, course_id)
    try:
        return request.app.state.quizzes.import_legacy_pack_quizzes(course_id, pack_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/{pack_id}/{action}", status_code=202, response_model=CourseStudyPack)
async def action(request: Request, course_id: str, pack_id: str, action: str):
    require_course(request, course_id)
    try:
        if action == "cancel":
            return await request.app.state.course_packs.cancel(course_id, pack_id)
        if action == "retry":
            return request.app.state.course_packs.retry(course_id, pack_id)
        raise HTTPException(404, "Unknown pack action")
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
