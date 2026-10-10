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


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or Settings()
    database = Database(app_settings.database_path)
    processor = LectureProcessor(app_settings, database)
    courses = CourseStore(database)
    documents = DocumentProcessor(app_settings, courses)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app_settings.prepare_directories()
        database.initialize()
        courses.initialize()
        await processor.start()
        await documents.start()
        yield
        await documents.stop()
        await processor.stop()

    app = FastAPI(title="PocketTA Local", version="0.1.0", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.database = database
    app.state.processor = processor
    app.state.courses = courses
    app.state.documents = documents
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    app.include_router(router)
    app.include_router(courses_router)
    return app


app = create_app()
