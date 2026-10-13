from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from .courses import require_course, require_source
from ..services.knowledge import EvidenceBundle

router = APIRouter(prefix="/api")


class SearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=6, ge=1, le=12)
    source_ids: list[str] | None = Field(default=None, min_length=1)

    @field_validator("query")
    @classmethod
    def clean_query(cls, value):
        if not value.strip():
            raise ValueError("Query must not be blank")
        return value.strip()


class TopicInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PrerequisiteInput(BaseModel):
    prerequisite_topic_id: str
    confidence: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)


@router.post("/courses/{course_id}/retrieve", response_model=EvidenceBundle)
async def retrieve(request: Request, course_id: str, payload: SearchInput):
    require_course(request, course_id)
    try:
        return await request.app.state.knowledge.retrieve(
            course_id, payload.query, payload.limit, payload.source_ids
        )
    except ValueError as error:
        raise HTTPException(404, str(error)) from error


class IndexInput(BaseModel):
    source_ids: list[str] = Field(min_length=1)


@router.post("/courses/{course_id}/index", status_code=202)
async def index_course(request: Request, course_id: str, payload: IndexInput):
    require_course(request, course_id)
    knowledge = request.app.state.knowledge
    try:
        selected = knowledge.validate_selection(course_id, payload.source_ids)
        for id in selected:
            if id in knowledge.pending or id in request.app.state.scheduler.jobs:
                raise ValueError("Source is already processing")
            if not request.app.state.courses.units(id):
                raise ValueError("Extract source content before indexing")
        for id in selected:
            knowledge.enqueue(id)
        return [knowledge.status(id) for id in selected]
    except ValueError as error:
        raise HTTPException(409, str(error)) from error


@router.get("/sources/{source_id}/knowledge")
def source_knowledge(request: Request, source_id: str):
    require_source(request, source_id)
    return request.app.state.knowledge.status(source_id)


@router.post("/courses/{course_id}/sources/{source_id}/index", status_code=202)
async def index_source(request: Request, course_id: str, source_id: str):
    require_course(request, course_id)
    source = require_source(request, source_id)
    if source["course_id"] != course_id:
        raise HTTPException(404, "Source not found in this course")
    try:
        request.app.state.knowledge.enqueue(source_id)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    return request.app.state.knowledge.status(source_id)


@router.get("/courses/{course_id}/topics")
def topics(request: Request, course_id: str):
    require_course(request, course_id)
    return request.app.state.knowledge.topics(course_id)


@router.post("/courses/{course_id}/topics", status_code=201)
def create_topic(request: Request, course_id: str, payload: TopicInput):
    require_course(request, course_id)
    topic = request.app.state.knowledge.upsert_topic(course_id, payload.name)
    if not topic:
        raise HTTPException(422, "Topic name must contain letters or numbers")
    return topic


@router.put("/courses/{course_id}/topics/{topic_id}/prerequisites")
def prerequisite(
    request: Request, course_id: str, topic_id: str, payload: PrerequisiteInput
):
    require_course(request, course_id)
    try:
        request.app.state.knowledge.link_prerequisite(
            course_id, topic_id, payload.prerequisite_topic_id, payload.confidence
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return request.app.state.knowledge.topics(course_id)
