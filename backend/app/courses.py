"""Course/source persistence. Lecture rows remain the legacy recording contract."""

from __future__ import annotations
import json
import uuid
from datetime import UTC, datetime
from .database import Database

IMPORT_COURSE = str(uuid.uuid5(uuid.NAMESPACE_URL, "pocketta:imported-lectures"))


class CourseStore:
    def __init__(self, db: Database):
        self.db = db

    def initialize(self):
        with self.db._connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS courses (id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id), name TEXT NOT NULL, type TEXT NOT NULL, file_path TEXT NOT NULL, status TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, error TEXT, progress INTEGER NOT NULL DEFAULT 0, pack_json TEXT, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS content_units (id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE, location TEXT NOT NULL, text TEXT NOT NULL, native_text TEXT NOT NULL DEFAULT '', vision_json TEXT, image_path TEXT, uncertain INTEGER NOT NULL DEFAULT 0, UNIQUE(source_id, location));
                CREATE TABLE IF NOT EXISTS model_runs (id TEXT PRIMARY KEY, source_id TEXT, provider TEXT, model TEXT, feature TEXT, prompt_version TEXT, latency REAL, usage_json TEXT, status TEXT, created_at TEXT);
            """)
            if c.execute(
                "SELECT 1 FROM lectures l LEFT JOIN sources s ON l.id=s.id WHERE s.id IS NULL LIMIT 1"
            ).fetchone():
                self._import_course(c)
                c.execute(
                    """INSERT OR IGNORE INTO sources(id, course_id, name, type, file_path, status, created_at)
                    SELECT id, ?, title, 'recording', source_path, status, created_at FROM lectures""",
                    (IMPORT_COURSE,),
                )

        with self.db._connect() as c:
            if "work_kind" not in {
                r["name"] for r in c.execute("PRAGMA table_info(sources)")
            }:
                c.execute(
                    "ALTER TABLE sources ADD COLUMN work_kind TEXT NOT NULL DEFAULT 'extract'"
                )
        with self.db._connect() as c:
            columns = {r["name"] for r in c.execute("PRAGMA table_info(model_runs)")}
            for name, declaration in {
                "course_id": "TEXT",
                "attempts": "INTEGER NOT NULL DEFAULT 1",
                "validation_status": "TEXT",
                "estimated_cost_usd": "REAL",
                "cost_rates_json": "TEXT",
            }.items():
                if name not in columns:
                    c.execute(f"ALTER TABLE model_runs ADD COLUMN {name} {declaration}")
        with self.db._connect() as c:
            if "confidence" not in {
                r["name"] for r in c.execute("PRAGMA table_info(content_units)")
            }:
                c.execute(
                    "ALTER TABLE content_units ADD COLUMN confidence REAL NOT NULL DEFAULT 1"
                )
        from .services.knowledge import initialize_knowledge

        initialize_knowledge(self.db)
        from .services.tutor import initialize_tutor

        initialize_tutor(self.db)
        for source in self.summaries(IMPORT_COURSE):
            self.sync_lecture_units(source["id"])

    def sync_lecture_units(self, id):
        lecture = self.db.get_lecture(id)
        mapping = {}
        if lecture and lecture.transcript:
            with self.db._connect() as c:
                for seg in lecture.transcript.segments:
                    location = f"time:{seg.start_ms}-{seg.end_ms}:{seg.id}"
                    unit_id = self.unit_id(id, location)
                    mapping[seg.id] = unit_id
                    c.execute(
                        """INSERT INTO content_units(id,source_id,location,text,native_text,uncertain,confidence)
                        VALUES (?,?,?,?,?,?,?) ON CONFLICT(source_id,location) DO UPDATE
                        SET text=excluded.text,native_text=excluded.native_text,uncertain=excluded.uncertain,confidence=excluded.confidence
                        WHERE content_units.text!=excluded.text OR content_units.uncertain!=excluded.uncertain OR content_units.confidence!=excluded.confidence""",
                        (
                            unit_id,
                            id,
                            location,
                            seg.text,
                            seg.text,
                            seg.uncertain,
                            seg.confidence,
                        ),
                    )
                current_ids = set(mapping.values())
                for row in c.execute(
                    "SELECT id FROM content_units WHERE source_id=?", (id,)
                ).fetchall():
                    if row["id"] not in current_ids:
                        c.execute("DELETE FROM content_units WHERE id=?", (row["id"],))
        return mapping

    @staticmethod
    def unit_id(source_id, location):
        return str(uuid.uuid5(uuid.NAMESPACE_URL, source_id + ":v1:" + location))

    def _import_course(self, c):
        c.execute(
            "INSERT OR IGNORE INTO courses VALUES (?, ?, ?, ?)",
            (
                IMPORT_COURSE,
                "Imported lectures",
                "Existing and unassigned recordings",
                datetime.now(UTC).isoformat(),
            ),
        )

    def attach_lecture(self, lecture_id, course_id=None):
        with self.db._connect() as c:
            if c.execute("SELECT 1 FROM sources WHERE id=?", (lecture_id,)).fetchone():
                return
        lecture = self.db.get_lecture(lecture_id)
        with self.db._connect() as c:
            if course_id is None:
                self._import_course(c)
            c.execute(
                "INSERT OR IGNORE INTO sources(id,course_id,name,type,file_path,status,created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    lecture_id,
                    course_id or IMPORT_COURSE,
                    lecture.title,
                    "recording",
                    str(self.db.get_source_path(lecture_id)),
                    lecture.status,
                    lecture.created_at.isoformat(),
                ),
            )

    def courses(self):
        with self.db._connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT courses.*, COUNT(sources.id) source_count FROM courses LEFT JOIN sources ON sources.course_id=courses.id GROUP BY courses.id ORDER BY courses.created_at DESC"
                )
            ]

    def course(self, id):
        with self.db._connect() as c:
            r = c.execute("SELECT * FROM courses WHERE id=?", (id,)).fetchone()
            return dict(r) if r else None

    def create_course(self, title, description):
        id = str(uuid.uuid4())
        with self.db._connect() as c:
            c.execute(
                "INSERT INTO courses VALUES (?,?,?,?)",
                (id, title, description, datetime.now(UTC).isoformat()),
            )
        return self.course(id)

    def sources(self, course_id):
        with self.db._connect() as c:
            ids = [
                r["id"]
                for r in c.execute(
                    "SELECT id FROM sources WHERE course_id=? ORDER BY created_at DESC",
                    (course_id,),
                )
            ]
        return [self.source(id) for id in ids]

    def summaries(self, course_id):
        with self.db._connect() as c:
            rows = c.execute(
                """SELECT s.id,s.course_id,COALESCE(l.title,s.name) name,s.type,
                COALESCE(l.status,s.status) status,COALESCE(l.progress,s.progress) progress,
                CASE WHEN s.type='recording' THEN l.error ELSE s.error END error,s.created_at,
                k.status knowledge_status,k.error knowledge_error
                FROM sources s LEFT JOIN lectures l ON s.id=l.id LEFT JOIN knowledge_index k ON k.source_id=s.id
                WHERE s.course_id=? ORDER BY s.created_at DESC""",
                (course_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def source(self, id):
        with self.db._connect() as c:
            r = c.execute("SELECT * FROM sources WHERE id=?", (id,)).fetchone()
        if not r:
            return None
        result = dict(r)
        result.pop("file_path")
        result["study_pack"] = (
            json.loads(result.pop("pack_json")) if r["pack_json"] else None
        )
        if r["type"] == "recording":
            lecture = self.db.get_lecture(id)
            if lecture:
                result.update(
                    name=lecture.title,
                    status=lecture.status,
                    progress=lecture.progress,
                    error=lecture.error,
                )
        if r["type"] == "recording":
            mapping = self.sync_lecture_units(id)
            if lecture and lecture.study_pack:
                pack = lecture.study_pack.model_dump()
                for key in ("notes", "concepts", "flashcards", "quiz"):
                    for item in pack[key]:
                        item["content_unit_ids"] = [
                            mapping[s] for s in item.pop("segment_ids") if s in mapping
                        ]
                result["study_pack"] = pack
        with self.db._connect() as c:
            knowledge = c.execute(
                "SELECT status,error,embedding_model FROM knowledge_index WHERE source_id=?",
                (id,),
            ).fetchone()
        result["knowledge"] = (
            dict(knowledge) if knowledge else {"status": "not_indexed", "error": None}
        )
        result["content_units"] = self.units(id)
        return result

    def path(self, id):
        with self.db._connect() as c:
            r = c.execute("SELECT file_path FROM sources WHERE id=?", (id,)).fetchone()
        return r["file_path"] if r else None

    def units(self, id):
        with self.db._connect() as c:
            return [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM content_units WHERE source_id=? ORDER BY rowid",
                    (id,),
                )
            ]

    def save_unit(self, source_id, location, text, native_text="", image_path=None):
        id = self.unit_id(source_id, location)
        with self.db._connect() as c:
            c.execute(
                "INSERT OR IGNORE INTO content_units(id,source_id,location,text,native_text,image_path) VALUES (?,?,?,?,?,?)",
                (id, source_id, location, text, native_text, image_path),
            )
        return id

    def update(self, id, status, progress=0, error=None):
        with self.db._connect() as c:
            c.execute(
                "UPDATE sources SET status=?,progress=?,error=? WHERE id=?",
                (status, progress, error, id),
            )
