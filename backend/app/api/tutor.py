from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .courses import require_course
from ..services.tutor import Intent
from ..services.generation import GenerationError

router = APIRouter(prefix="/api/courses/{course_id}/tutor")


class AskInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    intent: Intent = "explain"

    @field_validator("question")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Question must not be blank")
        return value.strip()


class CheckInput(BaseModel):
    response: str = Field(min_length=1, max_length=5000)

    @field_validator("response")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Response must not be blank")
        return value.strip()


@router.get("")
def history(request: Request, course_id: str):
    require_course(request, course_id)
    return request.app.state.tutor.history(course_id)


@router.post("", status_code=201)
async def ask(request: Request, course_id: str, payload: AskInput):
    require_course(request, course_id)
    try:
        return await request.app.state.tutor.ask(
            course_id, payload.question, payload.intent
        )
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    except GenerationError as error:
        raise HTTPException(
            503,
            "Tutor generation or verification unavailable. Check engine configuration and retry.",
        ) from error


@router.post("/{turn_id}/answer")
async def answer(request: Request, course_id: str, turn_id: str, payload: CheckInput):
    require_course(request, course_id)
    try:
        return await request.app.state.tutor.answer_check(
            course_id, turn_id, payload.response
        )
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    except GenerationError as error:
        raise HTTPException(
            503, "Grading unavailable. Check engine configuration and retry."
        ) from error
