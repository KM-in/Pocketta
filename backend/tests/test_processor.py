import os
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from backend.app.config import Settings
from backend.app.database import Database
from backend.app.courses import CourseStore
from backend.app.models import LectureStatus, ProcessingMetrics
from backend.app.services.processor import LectureProcessor
from backend.tests.test_models import study_pack, transcript


def prepared_processor(tmp_path: Path, lecture_id: str = "lecture") -> LectureProcessor:
    settings = Settings(pocketta_data_dir=tmp_path, temporary_file_max_age_hours=1)
    settings.prepare_directories()
    database = Database(settings.database_path)
    database.initialize()
    CourseStore(database).initialize()
    lecture_dir = settings.lectures_dir / lecture_id
    lecture_dir.mkdir()
    source = lecture_dir / "source.mp3"
    source.write_bytes(b"local")
    database.create_lecture(lecture_id, "source.mp3", source)
    return LectureProcessor(settings, database)


@pytest.mark.asyncio
async def test_queued_lecture_can_be_cancelled_without_deleting_data(
    tmp_path: Path,
) -> None:
    processor = prepared_processor(tmp_path)
    processor.enqueue("lecture")
    assert await processor.cancel("lecture") is True
    lecture = processor.database.get_lecture("lecture")
    assert lecture is not None
    assert lecture.status == LectureStatus.CANCELLED
    assert processor.database.get_source_path("lecture").is_file()


@pytest.mark.asyncio
async def test_generation_only_job_persists_metrics_and_completes(
    tmp_path: Path,
) -> None:
    processor = prepared_processor(tmp_path)
    processor.database.save_transcript("lecture", transcript())
    processor.database.save_metrics(
        "lecture",
        ProcessingMetrics(stage_seconds={"transcribing": 2.5}, total_seconds=2.5),
    )
    processor.database.update_status("lecture", LectureStatus.TRANSCRIBED)
    processor.lm_studio.generate = AsyncMock(
        side_effect=lambda evidence, **kwargs: study_pack(evidence.segments[0].id)
    )
    await processor.start()
    try:
        processor.enqueue_generation("lecture")
        await processor.queue.join()
    finally:
        await processor.stop()
    lecture = processor.database.get_lecture("lecture")
    assert lecture is not None
    assert lecture.status == LectureStatus.COMPLETED
    supplied = processor.lm_studio.generate.call_args.args[0]
    assert supplied.segments[0].id != "seg-0001"
    assert lecture.study_pack.notes[0].segment_ids == ["seg-0001"]
    assert "generating" in lecture.metrics.stage_seconds
    assert lecture.metrics.stage_seconds["transcribing"] == 2.5
    assert lecture.metrics.total_seconds >= 2.5


def test_startup_cleanup_removes_only_stale_temporary_files(tmp_path: Path) -> None:
    processor = prepared_processor(tmp_path)
    lecture_dir = processor.settings.lectures_dir / "lecture"
    stale = lecture_dir / "audio.wav"
    fresh = lecture_dir / "whisper.json"
    stale.write_bytes(b"stale")
    fresh.write_text("{}", encoding="utf-8")
    old = time.time() - 7200
    os.utime(stale, (old, old))
    processor._cleanup_temporary_files()
    assert not stale.exists()
    assert fresh.exists()
