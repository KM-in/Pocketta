from __future__ import annotations

import asyncio
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from ..config import Settings
from ..database import Database
from ..models import LectureStatus, ProcessingMetrics
from .gateway import ModelGateway
from .scheduler import CourseScheduler
from ..courses import CourseStore
from .media import MediaService
from .processes import ProcessRegistry
from .whisper import TranscriptionService


class LectureCancelled(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkItem:
    lecture_id: str
    generation_only: bool = False


@dataclass
class RunMetrics:
    started: float = field(default_factory=time.perf_counter)
    base_total_seconds: float = 0
    stage: str | None = None
    stage_started: float | None = None
    stage_seconds: dict[str, float] = field(default_factory=dict)
    peak_system_memory_mb: float = 0

    def begin(self, stage: str) -> None:
        self.finish_stage()
        self.stage = stage
        self.stage_started = time.perf_counter()

    def finish_stage(self) -> None:
        if self.stage and self.stage_started is not None:
            elapsed = time.perf_counter() - self.stage_started
            self.stage_seconds[self.stage] = round(
                self.stage_seconds.get(self.stage, 0) + elapsed, 3
            )
        self.stage = None
        self.stage_started = None

    def snapshot(self) -> ProcessingMetrics:
        stage_seconds = dict(self.stage_seconds)
        if self.stage and self.stage_started is not None:
            stage_seconds[self.stage] = round(
                stage_seconds.get(self.stage, 0)
                + time.perf_counter()
                - self.stage_started,
                3,
            )
        return ProcessingMetrics(
            stage_seconds=stage_seconds,
            total_seconds=round(
                self.base_total_seconds + time.perf_counter() - self.started, 3
            ),
            peak_system_memory_mb=round(self.peak_system_memory_mb, 1),
        )


class LectureProcessor:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        scheduler=None,
        coordinator=None,
        knowledge=None,
    ):
        self.settings = settings
        self.database = database
        if knowledge is None:
            from .knowledge import KnowledgeService

            knowledge = KnowledgeService(
                settings, CourseStore(database), coordinator=coordinator
            )
        self.knowledge = knowledge
        self.scheduler = scheduler or CourseScheduler(settings)
        self.owns_scheduler = scheduler is None
        self.queue: asyncio.Queue[WorkItem] = asyncio.Queue()
        self.processes = ProcessRegistry()
        self.media = MediaService(settings, self.processes)
        self.transcription = TranscriptionService(settings, self.processes)
        self.lm_studio = ModelGateway(settings, database, coordinator=coordinator)
        self.cancelled: set[str] = set()
        self.queued_ids: set[str] = set()
        self.active_tasks: dict[str, asyncio.Task[None]] = {}

    async def blocking(self, fn, *args):
        # Cancellation cannot abandon a native thread that still owns source files.
        task = asyncio.create_task(asyncio.to_thread(fn, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await task
            except Exception:
                pass
            raise

    async def start(self) -> None:
        CourseStore(self.database).initialize()
        await asyncio.to_thread(self._cleanup_temporary_files)
        for lecture_id in self.database.recover_incomplete():
            lecture = self.database.get_lecture(lecture_id)
            self.enqueue(
                lecture_id, generation_only=bool(lecture and lecture.transcript)
            )
        if self.owns_scheduler:
            await self.scheduler.start()

    async def stop(self) -> None:
        if self.owns_scheduler:
            self.scheduler.running = False
        for lecture_id in list(self.queued_ids | self.active_tasks.keys()):
            await asyncio.to_thread(self.processes.terminate, lecture_id)
            await self.scheduler.cancel(lecture_id)
        if self.owns_scheduler:
            await self.scheduler.stop()

    def enqueue(self, lecture_id: str, *, generation_only: bool = False) -> None:
        if self.is_processing(lecture_id):
            raise ValueError("Lecture is already processing")
        store = CourseStore(self.database)
        store.attach_lecture(lecture_id)
        self.queued_ids.add(lecture_id)
        item = WorkItem(lecture_id, generation_only)
        self.queue.put_nowait(item)
        with self.database._connect() as c:
            row = c.execute(
                "SELECT course_id FROM sources WHERE id=?", (lecture_id,)
            ).fetchone()
        self.scheduler.submit(
            lecture_id,
            row["course_id"] if row else "legacy",
            lambda: self._run_job(item),
            lambda: self._job_done(lecture_id),
        )

    def is_processing(self, lecture_id: str) -> bool:
        return (
            lecture_id in self.queued_ids
            or lecture_id in self.active_tasks
            or f"knowledge:{lecture_id}" in self.scheduler.jobs
        )

    async def cancel(self, lecture_id: str) -> bool:
        lecture = self.database.get_lecture(lecture_id)
        if not lecture:
            return False
        if not self.is_processing(lecture_id):
            raise ValueError("Lecture is not currently processing")
        if f"knowledge:{lecture_id}" in self.scheduler.jobs:
            await self.scheduler.cancel(f"knowledge:{lecture_id}")
            self.knowledge.set_status(lecture_id, "cancelled")
            return True
        self.cancelled.add(lecture_id)
        self.database.update_status(
            lecture_id,
            LectureStatus.CANCELLED,
            progress=lecture.progress,
            message="Processing cancelled; local results were retained",
        )
        await asyncio.to_thread(self.processes.terminate, lecture_id)
        await self.scheduler.cancel(lecture_id)
        return True

    def enqueue_generation(self, lecture_id: str) -> None:
        lecture = self.database.get_lecture(lecture_id)
        if not lecture:
            raise KeyError(lecture_id)
        if self.is_processing(lecture_id):
            raise ValueError("Lecture is already processing")
        if not lecture.transcript:
            raise ValueError("A transcript is required before generation")
        self.database.clear_study_pack(lecture_id)
        study_pack_path = self.settings.lectures_dir / lecture_id / "study_pack.json"
        study_pack_path.unlink(missing_ok=True)
        self.database.update_status(
            lecture_id,
            LectureStatus.QUEUED,
            progress=60,
            message="Waiting to build the study pack",
        )
        self.enqueue(lecture_id, generation_only=True)

    async def delete(self, lecture_id: str) -> bool:
        await self.scheduler.cancel(f"knowledge:{lecture_id}")
        if not self.database.exists(lecture_id):
            return False
        self.cancelled.add(lecture_id)
        self.database.update_status(
            lecture_id,
            LectureStatus.DELETING,
            progress=0,
            message="Deleting local files and results",
        )
        await asyncio.to_thread(self.processes.terminate, lecture_id)
        await self.scheduler.cancel(lecture_id)
        lecture_dir = self.settings.lectures_dir / lecture_id
        await asyncio.to_thread(shutil.rmtree, lecture_dir, True)
        return self.database.delete(lecture_id)

    def _job_done(self, lecture_id):
        self.queued_ids.discard(lecture_id)
        self.active_tasks.pop(lecture_id, None)
        self.cancelled.discard(lecture_id)
        self.queue.get_nowait()
        self.queue.task_done()

    async def _run_job(self, item):
        lecture_id = item.lecture_id
        self.queued_ids.discard(lecture_id)
        self.active_tasks[lecture_id] = asyncio.current_task()
        try:
            self._check(lecture_id)
            await self._process(item)
        except (LectureCancelled, asyncio.CancelledError):
            raise
        except Exception as error:
            if self.database.exists(lecture_id):
                self.database.update_status(
                    lecture_id,
                    LectureStatus.FAILED,
                    _safe_error(error),
                    message="Processing stopped; review the error and retry if possible",
                )

    async def _process(self, item: WorkItem) -> None:
        lecture_id = item.lecture_id
        existing = self.database.get_lecture(lecture_id)
        metrics = RunMetrics(
            base_total_seconds=existing.metrics.total_seconds if existing else 0,
            stage_seconds=dict(existing.metrics.stage_seconds) if existing else {},
            peak_system_memory_mb=(
                existing.metrics.peak_system_memory_mb if existing else 0
            ),
        )
        monitor = asyncio.create_task(self._monitor_memory(metrics))
        try:
            if item.generation_only:
                lecture = self.database.get_lecture(lecture_id)
                if not lecture or not lecture.transcript:
                    raise ValueError("The saved transcript is unavailable")
                transcript = lecture.transcript
            else:
                source = self.database.get_source_path(lecture_id)
                if not source:
                    raise LectureCancelled()
                lecture_dir = self.settings.lectures_dir / lecture_id
                normalized = lecture_dir / "audio.wav"

                self._check(lecture_id)
                self._begin_stage(
                    lecture_id,
                    metrics,
                    "normalizing",
                    LectureStatus.NORMALIZING,
                    5,
                    "Preparing a private 16 kHz audio copy",
                )
                duration_ms = await self.blocking(
                    self.media.normalize, lecture_id, source, normalized
                )

                self._check(lecture_id)
                self._begin_stage(
                    lecture_id,
                    metrics,
                    "transcribing",
                    LectureStatus.TRANSCRIBING,
                    20,
                    "Transcribing locally with "
                    + (
                        "Faster Whisper"
                        if self.transcription.selected_backend() == "faster_whisper"
                        else "whisper.cpp"
                    ),
                )
                transcript = await self.blocking(
                    self.transcription.transcribe, lecture_id, normalized, duration_ms
                )
                self._check(lecture_id)
                self.database.save_transcript(lecture_id, transcript)
                (lecture_dir / "transcript.json").write_text(
                    transcript.model_dump_json(indent=2), encoding="utf-8"
                )
                normalized.unlink(missing_ok=True)
                (lecture_dir / "whisper.json").unlink(missing_ok=True)

            self._check(lecture_id)
            self._begin_stage(
                lecture_id,
                metrics,
                "generating",
                LectureStatus.GENERATING,
                60,
                "Building grounded notes, cards, and questions",
            )
            store = CourseStore(self.database)
            store.attach_lecture(lecture_id)
            mapping = store.sync_lecture_units(lecture_id)
            source_path = Path(self.database.get_source_path(lecture_id) or "")
            video_extensions = {".mp4", ".mkv", ".mov", ".webm"}
            if (
                not item.generation_only
                and self.settings.model_provider == "cerebras"
                and source_path.suffix.lower() in video_extensions
            ):
                frames = await self.blocking(
                    self.media.extract_video_frames,
                    lecture_id,
                    source_path,
                    self.settings.lectures_dir / lecture_id / "frames",
                    transcript.duration_ms,
                )
                frame_gateway = ModelGateway(
                    self.settings,
                    self.database,
                    lecture_id,
                    coordinator=self.lm_studio.coordinator,
                )
                for offset_ms, image_path in frames:
                    location = f"time:{offset_ms}-{offset_ms}:frame-{offset_ms}"
                    unit_id = store.save_unit(
                        lecture_id, location, "", "", str(image_path)
                    )
                    try:
                        visual = await frame_gateway.analyse_image(
                            image_path,
                            "Describe only visually clear educational content in this video frame. "
                            "Transcribe readable labels and explain diagrams without adding facts not visible. "
                            "Set uncertain when text or a material detail is unclear.",
                        )
                        description = "\n".join(
                            part for part in (visual.transcription, visual.description) if part
                        )
                        uncertain = visual.uncertain or not description.strip()
                        saved_vision = visual.model_dump()
                    except Exception:
                        description, uncertain = "", True
                        saved_vision = {
                            "transcription": "",
                            "description": "",
                            "uncertain": True,
                            "analysis_unavailable": True,
                        }
                    with self.database._connect() as c:
                        c.execute(
                            "UPDATE content_units SET text=?,vision_json=?,uncertain=? WHERE id=?",
                            (description, json.dumps(saved_vision), uncertain, unit_id),
                        )
            await self.knowledge.index_source(lecture_id)
            self._check(lecture_id)
            grounded = transcript.model_copy(deep=True)
            for segment in grounded.segments:
                segment.id = mapping[segment.id]
            study_pack = await self.lm_studio.generate(grounded, source_id=lecture_id)
            study_pack.validate_evidence(grounded)
            inverse = {v: k for k, v in mapping.items()}
            # The legacy API retains segment IDs; course APIs resolve them to UUID units.
            for collection in (
                study_pack.notes,
                study_pack.concepts,
                study_pack.flashcards,
                study_pack.quiz,
            ):
                for entry in collection:
                    entry.segment_ids = [inverse[id] for id in entry.segment_ids]
            self._check(lecture_id)
            self.database.save_study_pack(lecture_id, study_pack)
            lecture_dir = self.settings.lectures_dir / lecture_id
            (lecture_dir / "study_pack.json").write_text(
                study_pack.model_dump_json(indent=2), encoding="utf-8"
            )
            metrics.finish_stage()
            self.database.save_metrics(lecture_id, metrics.snapshot())
            self.database.update_status(
                lecture_id,
                LectureStatus.COMPLETED,
                progress=100,
                message="Study pack ready",
            )
        finally:
            monitor.cancel()
            try:
                await monitor
            except asyncio.CancelledError:
                pass
            if self.database.exists(lecture_id):
                self.database.save_metrics(lecture_id, metrics.snapshot())

    def _begin_stage(
        self,
        lecture_id: str,
        metrics: RunMetrics,
        stage: str,
        status: LectureStatus,
        progress: int,
        message: str,
    ) -> None:
        metrics.begin(stage)
        self.database.save_metrics(lecture_id, metrics.snapshot())
        self.database.update_status(
            lecture_id, status, progress=progress, message=message
        )

    async def _monitor_memory(self, metrics: RunMetrics) -> None:
        while True:
            used_mb = psutil.virtual_memory().used / (1024 * 1024)
            metrics.peak_system_memory_mb = max(metrics.peak_system_memory_mb, used_mb)
            await asyncio.sleep(0.25)

    def _check(self, lecture_id: str) -> None:
        if lecture_id in self.cancelled or not self.database.exists(lecture_id):
            raise LectureCancelled()

    def _cleanup_temporary_files(self) -> None:
        cutoff = time.time() - self.settings.temporary_file_max_age_hours * 3600
        for pattern in ("audio.wav", "whisper.json", "*.tmp"):
            for path in self.settings.lectures_dir.glob(f"*/{pattern}"):
                try:
                    if path.stat().st_mtime < cutoff:
                        path.unlink(missing_ok=True)
                except OSError:
                    continue


def _safe_error(error: Exception) -> str:
    text = str(error).strip() or error.__class__.__name__
    return text[-2000:]
