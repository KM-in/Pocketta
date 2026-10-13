from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.lectures import router
from .config import Settings
from .database import Database
from .courses import CourseStore
from .api.courses import router as courses_router
from .services.documents import DocumentProcessor
from .services.processor import LectureProcessor
from .services.scheduler import CourseScheduler
from .services.providers import RequestCoordinator
from .services.knowledge import KnowledgeService
from .api.knowledge import router as knowledge_router
from .api.tutor import router as tutor_router
from .services.tutor import TutorService
from .services.course_packs import CoursePackService
from .api.course_packs import router as course_packs_router
from .services.quizzes import QuizService
from .api.quizzes import router as quizzes_router


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    database = Database(app_settings.database_path)
    scheduler = CourseScheduler(app_settings)
    coordinator = RequestCoordinator(app_settings)
    courses = CourseStore(database)
    knowledge = KnowledgeService(app_settings, courses, scheduler, coordinator)
    processor = LectureProcessor(
        app_settings, database, scheduler, coordinator, knowledge
    )
    documents = DocumentProcessor(
        app_settings, courses, scheduler, coordinator, knowledge
    )
    course_packs = CoursePackService(
        app_settings, courses, knowledge, scheduler, coordinator
    )
    quizzes = QuizService(app_settings, courses, knowledge, coordinator)
    course_packs.quizzes = quizzes

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings.prepare_directories()
        database.initialize()
        courses.initialize()
        await processor.start()
        await documents.start()
        await knowledge.start()
        await course_packs.start()
        await scheduler.start()
        try:
            yield
        finally:
            scheduler.running = False
            await course_packs.stop()
            await knowledge.stop()
            await documents.stop()
            await processor.stop()
            await scheduler.stop()

    app = FastAPI(title="PocketTA Local", version="0.1.0", lifespan=lifespan)
    app.state.tutor = TutorService(app_settings, courses, knowledge, coordinator)
    app.state.knowledge = knowledge
    app.state.scheduler = scheduler
    app.state.coordinator = coordinator
    app.state.settings = app_settings
    app.state.database = database
    app.state.processor = processor
    app.state.courses = courses
    app.state.documents = documents
    app.state.course_packs = course_packs
    app.state.quizzes = quizzes
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(courses_router)
    app.include_router(knowledge_router)
    app.include_router(tutor_router)
    app.include_router(course_packs_router)
    app.include_router(quizzes_router)
    return app


app = create_app()
