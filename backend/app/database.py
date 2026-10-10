from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from .models import (
    LectureDetail,
    LectureStatus,
    LectureSummary,
    ProcessingMetrics,
    StudyPack,
    Transcript,
)


class Database:
    def __init__(self, path: Path):
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS lectures (
                    id TEXT PRIMARY KEY,
                    original_filename TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    transcript_json TEXT,
                    study_pack_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """)
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(lectures)").fetchall()
            }
            migrations = {
                "title": "ALTER TABLE lectures ADD COLUMN title TEXT",
                "progress": (
                    "ALTER TABLE lectures ADD COLUMN progress INTEGER NOT NULL DEFAULT 0"
                ),
                "message": (
                    "ALTER TABLE lectures ADD COLUMN message TEXT NOT NULL DEFAULT ''"
                ),
                "metrics_json": "ALTER TABLE lectures ADD COLUMN metrics_json TEXT",
            }
            for column, statement in migrations.items():
                if column not in columns:
                    connection.execute(statement)
            connection.execute(
                "UPDATE lectures SET title = original_filename WHERE title IS NULL OR title = ''"
            )

    def create_lecture(
        self,
        lecture_id: str,
        filename: str,
        source_path: Path,
        title: str | None = None,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        display_title = (
            title.strip() if title and title.strip() else Path(filename).stem
        )
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO lectures
                (id, title, original_filename, source_path, status, progress, message,
                 created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lecture_id,
                    display_title,
                    filename,
                    str(source_path),
                    LectureStatus.QUEUED,
                    0,
                    "Waiting for the local worker",
                    now,
                    now,
                ),
            )

    def update_status(
        self,
        lecture_id: str,
        status: LectureStatus,
        error: str | None = None,
        *,
        progress: int | None = None,
        message: str | None = None,
    ) -> bool:
        assignments = ["status = ?", "error = ?", "updated_at = ?"]
        values: list[object] = [status, error, datetime.now(UTC).isoformat()]
        if progress is not None:
            assignments.append("progress = ?")
            values.append(max(0, min(100, progress)))
        if message is not None:
            assignments.append("message = ?")
            values.append(message)
        values.append(lecture_id)
        with self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE lectures SET {', '.join(assignments)} WHERE id = ?", values
            )
            return cursor.rowcount > 0

    def save_metrics(self, lecture_id: str, metrics: ProcessingMetrics) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE lectures SET metrics_json = ?, updated_at = ? WHERE id = ?",
                (metrics.model_dump_json(), datetime.now(UTC).isoformat(), lecture_id),
            )

    def update_title(self, lecture_id: str, title: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE lectures SET title = ?, updated_at = ? WHERE id = ?",
                (title, datetime.now(UTC).isoformat(), lecture_id),
            )

    def save_transcript(self, lecture_id: str, transcript: Transcript) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE lectures SET transcript_json = ?, updated_at = ? WHERE id = ?",
                (
                    transcript.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                    lecture_id,
                ),
            )

    def replace_transcript_and_invalidate_pack(
        self, lecture_id: str, transcript: Transcript
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE lectures
                SET transcript_json = ?, study_pack_json = NULL, status = ?, error = NULL,
                    progress = 60, message = ?, updated_at = ?
                WHERE id = ?""",
                (
                    transcript.model_dump_json(),
                    LectureStatus.TRANSCRIBED,
                    "Transcript updated; regenerate the study pack",
                    datetime.now(UTC).isoformat(),
                    lecture_id,
                ),
            )

    def clear_study_pack(self, lecture_id: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE lectures SET study_pack_json = NULL, updated_at = ? WHERE id = ?",
                (datetime.now(UTC).isoformat(), lecture_id),
            )

    def save_study_pack(self, lecture_id: str, study_pack: StudyPack) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE lectures SET study_pack_json = ?, updated_at = ? WHERE id = ?",
                (
                    study_pack.model_dump_json(),
                    datetime.now(UTC).isoformat(),
                    lecture_id,
                ),
            )

    def get_source_path(self, lecture_id: str) -> Path | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT source_path FROM lectures WHERE id = ?", (lecture_id,)
            ).fetchone()
        return Path(row["source_path"]) if row else None

    def exists(self, lecture_id: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM lectures WHERE id = ?", (lecture_id,)
            ).fetchone()
        return row is not None

    def list_lectures(self) -> list[LectureSummary]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM lectures ORDER BY created_at DESC"
            ).fetchall()
        return [self._summary(row) for row in rows]

    def get_lecture(self, lecture_id: str) -> LectureDetail | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM lectures WHERE id = ?", (lecture_id,)
            ).fetchone()
        if not row:
            return None
        return LectureDetail(
            **self._summary(row).model_dump(),
            transcript=(
                Transcript.model_validate_json(row["transcript_json"])
                if row["transcript_json"]
                else None
            ),
            study_pack=(
                StudyPack.model_validate_json(row["study_pack_json"])
                if row["study_pack_json"]
                else None
            ),
        )

    def recover_incomplete(self) -> list[str]:
        active = (
            LectureStatus.QUEUED,
            LectureStatus.NORMALIZING,
            LectureStatus.TRANSCRIBING,
            LectureStatus.GENERATING,
        )
        placeholders = ",".join("?" for _ in active)
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT id FROM lectures WHERE status IN ({placeholders})", active
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                connection.executemany(
                    """UPDATE lectures SET status = ?, error = NULL, progress = 0,
                    message = ?, updated_at = ? WHERE id = ?""",
                    [
                        (
                            LectureStatus.QUEUED,
                            "Recovered after restart",
                            datetime.now(UTC).isoformat(),
                            lecture_id,
                        )
                        for lecture_id in ids
                    ],
                )
        return ids

    def delete(self, lecture_id: str) -> bool:
        with self._connect() as connection:
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE name='sources'"
            ).fetchone():
                connection.execute(
                    "DELETE FROM model_runs WHERE source_id = ?", (lecture_id,)
                )
                connection.execute("DELETE FROM sources WHERE id = ?", (lecture_id,))
            cursor = connection.execute(
                "DELETE FROM lectures WHERE id = ?", (lecture_id,)
            )
            return cursor.rowcount > 0

    @staticmethod
    def _summary(row: sqlite3.Row) -> LectureSummary:
        return LectureSummary(
            id=row["id"],
            title=row["title"] or Path(row["original_filename"]).stem,
            original_filename=row["original_filename"],
            status=row["status"],
            progress=row["progress"] or 0,
            message=row["message"] or "",
            metrics=(
                ProcessingMetrics.model_validate_json(row["metrics_json"])
                if row["metrics_json"]
                else ProcessingMetrics()
            ),
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
