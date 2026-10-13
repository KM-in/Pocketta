import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..services.generation import GenerationError
from .courses import require_course

router = APIRouter(prefix="/api/courses/{course_id}")


class QuizInput(BaseModel):
    source_ids: list[str] = Field(min_length=1)
    question_count: int = Field(default=10, ge=1, le=50)
    mcq_count: int = Field(default=6, ge=0, le=50)
    numerical_count: int = Field(default=0, ge=0, le=50)
    difficulty: Literal["adaptive", "easy", "medium", "challenging"] = "adaptive"
    desired_topics: list[str] = Field(default_factory=list, max_length=30)
    excluded_topics: list[str] = Field(default_factory=list, max_length=30)
    instructions: str = Field(default="", max_length=3000)


class AnswersInput(BaseModel):
    answers: dict[str, str]


class SyllabusInput(BaseModel):
    markdown: str = Field(min_length=1, max_length=100000)


class SyllabusMapping(BaseModel):
    topic_id: str
    source_ids: list[str] = Field(default_factory=list)


class MappingInput(BaseModel):
    mappings: list[SyllabusMapping]


class StudiedInput(BaseModel):
    studied: bool


@router.get("/quizzes")
def quizzes(request: Request, course_id: str):
    require_course(request, course_id)
    return request.app.state.quizzes.list_quizzes(course_id)


@router.post("/quizzes", status_code=201)
async def create_quiz(request: Request, course_id: str, payload: QuizInput):
    require_course(request, course_id)
    try:
        return await request.app.state.quizzes.generate(
            course_id, **payload.model_dump()
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    except GenerationError as error:
        raise HTTPException(
            503,
            "Quiz generation or verification unavailable; retry after checking the model configuration",
        ) from error


@router.get("/quizzes/{quiz_id}")
def get_quiz(request: Request, course_id: str, quiz_id: str):
    require_course(request, course_id)
    try:
        return request.app.state.quizzes.get_quiz(course_id, quiz_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@router.post("/quizzes/{quiz_id}/retry")
async def retry_quiz(request: Request, course_id: str, quiz_id: str):
    require_course(request, course_id)
    try:
        with request.app.state.database._connect() as c:
            row = c.execute(
                "SELECT * FROM course_quizzes WHERE id=? AND course_id=?",
                (quiz_id, course_id),
            ).fetchone()
        if not row:
            raise LookupError("Quiz not found in this course")
        opts = json.loads(row["instructions_json"])
        prior_questions = json.loads(row["questions_json"])
        return await request.app.state.quizzes.generate(
            course_id,
            [s["id"] for s in json.loads(row["snapshots_json"])],
            question_count=opts.get("question_count", len(prior_questions)),
            mcq_count=opts.get(
                "mcq_count", sum(q["kind"] == "mcq" for q in prior_questions)
            ),
            numerical_count=opts.get(
                "numerical_count", sum(q["kind"] == "numerical" for q in prior_questions)
            ),
            difficulty=opts.get("difficulty", "adaptive"),
            desired_topics=opts.get("desired_topics", []),
            excluded_topics=opts.get("excluded_topics", []),
            instructions=opts.get("instructions", ""),
            fixed_topics=list(dict.fromkeys(q["topic"] for q in prior_questions)),
        )
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/quizzes/{quiz_id}/attempts", status_code=201)
def create_attempt(request: Request, course_id: str, quiz_id: str):
    require_course(request, course_id)
    try:
        return request.app.state.quizzes.create_attempt(course_id, quiz_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/quiz-attempts/{attempt_id}")
def get_attempt(request: Request, course_id: str, attempt_id: str):
    require_course(request, course_id)
    try:
        return request.app.state.quizzes.attempt(course_id, attempt_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error


@router.put("/quiz-attempts/{attempt_id}/answers")
def save_answers(
    request: Request, course_id: str, attempt_id: str, payload: AnswersInput
):
    require_course(request, course_id)
    try:
        return request.app.state.quizzes.save_answers(
            course_id, attempt_id, payload.answers
        )
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/quiz-attempts/{attempt_id}/submit")
async def submit_attempt(request: Request, course_id: str, attempt_id: str):
    require_course(request, course_id)
    try:
        return await request.app.state.quizzes.submit(course_id, attempt_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    except GenerationError as error:
        raise HTTPException(
            503,
            "Short-answer grading failed; your answers are saved. Retry grading to continue.",
        ) from error


@router.get("/learning")
def learning(request: Request, course_id: str):
    require_course(request, course_id)
    return request.app.state.quizzes.learning(course_id)


@router.get("/learning/user_learning.md")
def learning_report(request: Request, course_id: str):
    require_course(request, course_id)
    path = request.app.state.quizzes.report_path(course_id)
    return FileResponse(path, media_type="text/markdown", filename="user_learning.md")


@router.get("/syllabus")
def get_syllabus(request: Request, course_id: str):
    require_course(request, course_id)
    return request.app.state.quizzes.syllabus(course_id)


@router.get("/syllabus.md")
def download_syllabus(request: Request, course_id: str):
    require_course(request, course_id)
    path = (
        request.app.state.settings.pocketta_data_dir
        / "courses"
        / course_id
        / "syllabus.md"
    )
    if not path.exists():
        raise HTTPException(404, "No syllabus has been saved for this course")
    return FileResponse(path, media_type="text/markdown", filename="syllabus.md")


@router.put("/syllabus")
async def put_syllabus(request: Request, course_id: str, payload: SyllabusInput):
    require_course(request, course_id)
    try:
        return await request.app.state.quizzes.save_syllabus(
            course_id, payload.markdown
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@router.post("/syllabus/confirm")
def confirm_syllabus(request: Request, course_id: str, payload: MappingInput):
    require_course(request, course_id)
    try:
        return request.app.state.quizzes.confirm_syllabus(
            course_id, [mapping.model_dump() for mapping in payload.mappings]
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.patch("/syllabus/topics/{topic_id}/studied")
def mark_studied(
    request: Request, course_id: str, topic_id: str, payload: StudiedInput
):
    require_course(request, course_id)
    try:
        return request.app.state.quizzes.mark_studied(
            course_id, topic_id, payload.studied
        )
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
