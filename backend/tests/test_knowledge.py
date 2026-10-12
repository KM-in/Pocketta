import asyncio
import json
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.courses import CourseStore
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.services.gateway import ModelGateway
from backend.app.services.knowledge import (
    KnowledgeService,
    chunk_text,
    location_citation,
)
from backend.app.tools.evaluate_retrieval import FIXTURE, evaluate, seed_fixture


@pytest.fixture
def library(tmp_path):
    config = Settings(_env_file=None, pocketta_data_dir=tmp_path, openai_api_key="")
    db = Database(config.database_path)
    db.initialize()
    store = CourseStore(db)
    store.initialize()
    fixture = json.loads(FIXTURE.read_text())
    course, locations = seed_fixture(store, fixture)
    return config, store, course, locations, fixture


async def index_all(service, course_id):
    for source in service.store.sources(course_id):
        await service.index_source(source["id"])


def test_chunk_offsets_and_overlap():
    text = "Operating systems manage processes and resources. " * 90
    chunks = list(chunk_text(text, 300, 40))
    assert len(chunks) > 1 and chunks[0][0] == 0 and chunks[-1][1] == len(text)
    for start, end, excerpt in chunks:
        assert excerpt == text[start:end] and len(excerpt) <= 300
    assert all(next_[0] <= prev[1] for prev, next_ in zip(chunks, chunks[1:]))
    assert list(chunk_text("", 300, 40)) == []


@pytest.mark.asyncio
async def test_held_out_keyword_locations_and_uncertainty(library):
    config, store, course, locations, fixture = library
    service = KnowledgeService(config, store)
    await index_all(service, course["id"])
    for question in fixture["questions"]:
        result = await service.retrieve(course["id"], question["query"])
        actual = {item.content_unit_id for item in result.items}
        expected = {
            locations[(item["source"], item["location"])]
            for item in question["expected"]
        }
        assert expected.issubset(actual)
        if not expected:
            assert result.coverage == "unsupported" and not actual
        for item in result.items:
            unit = next(
                unit
                for unit in store.units(item.source_id)
                if unit["id"] == item.content_unit_id
            )
            assert item.excerpt == unit["text"][item.char_start : item.char_end]
            assert item.citation == location_citation(unit["location"])
    assert locations[("textbook", "page:99")] not in actual


@pytest.mark.asyncio
async def test_stable_chunks_topics_and_edit_version_invalidation(library):
    config, store, course, locations, _ = library
    service = KnowledgeService(config, store)
    await index_all(service, course["id"])
    before = await service.retrieve(course["id"], "deadlock")
    source_id = before.items[0].source_id
    topic_ids = {t["id"] for t in service.topics(course["id"])["topics"]}
    await service.index_source(source_id)
    after = await service.retrieve(course["id"], "deadlock")
    assert before.items[0].chunk_id == after.items[0].chunk_id
    assert topic_ids == {t["id"] for t in service.topics(course["id"])["topics"]}
    with store.db._connect() as c:
        c.execute(
            "UPDATE content_units SET text='Semaphores coordinate access.' WHERE id=?",
            (locations[("textbook", "page:44")],),
        )
        c.execute("UPDATE sources SET version=version+1 WHERE id=?", (source_id,))
    assert service.status(source_id)["status"] == "stale"
    assert not (await service.retrieve(course["id"], "deadlock")).items
    await service.index_source(source_id)
    revised = await service.retrieve(course["id"], "semaphores")
    assert revised.items[0].source_version == 2
    assert revised.items[0].chunk_id != before.items[0].chunk_id


@pytest.mark.asyncio
async def test_hybrid_paraphrase_and_course_isolation(library, monkeypatch):
    config, store, course, locations, _ = library
    config.openai_api_key = "fake"

    async def embed(self, texts):
        return [
            (
                [1.0, 0.0]
                if any(word in text.lower() for word in ("mutex", "locking"))
                else [0.0, 1.0]
            )
            for text in texts
        ]

    monkeypatch.setattr(ModelGateway, "embed", embed)
    service = KnowledgeService(config, store)
    await index_all(service, course["id"])
    other, _ = seed_fixture(store, json.loads(FIXTURE.read_text()))
    await index_all(service, other["id"])
    result = await service.retrieve(course["id"], "locking")
    assert result.retrieval_mode == "hybrid"
    assert (
        result.items[0].content_unit_id
        == locations[("lecture", "time:62000-79000:seg-0004")]
    )
    course_sources = {s["id"] for s in store.sources(course["id"])}
    assert all(item.source_id in course_sources for item in result.items)
    assert result.items[0].citation.start_sec == 62
    assert result.items[0].citation.end_sec == 79
    empty = store.create_course("Empty", "")
    assert not (await service.retrieve(empty["id"], "locking")).items


@pytest.mark.asyncio
async def test_embedding_failure_falls_back_and_retry_can_recover(library, monkeypatch):
    config, store, course, _, _ = library
    config.openai_api_key = "fake"
    monkeypatch.setattr(
        ModelGateway,
        "embed",
        AsyncMock(side_effect=RuntimeError("provider private details")),
    )
    service = KnowledgeService(config, store)
    await index_all(service, course["id"])
    result = await service.retrieve(course["id"], "deadlock")
    source_id = result.items[0].source_id
    state = service.status(source_id)
    assert state["status"] == "keyword_ready" and "private" not in state["error"]
    monkeypatch.setattr(
        ModelGateway,
        "embed",
        AsyncMock(side_effect=lambda texts: [[1.0, 0.0] for _ in texts]),
    )
    await service.index_source(source_id)
    assert service.status(source_id)["status"] == "ready"


@pytest.mark.asyncio
async def test_prerequisite_membership_manual_precedence_and_inferred_links(
    library, monkeypatch
):
    config, store, course, _, _ = library
    config.knowledge_infer_topics = True

    async def infer(self, prompt, schema, **kwargs):
        chunks = json.loads(prompt.split("\n", 1)[1])
        return {
            "tags": [
                {"chunk_id": ch["chunk_id"], "topics": ["Processes", "Threads"]}
                for ch in chunks
            ],
            "prerequisites": [
                {"topic": "Threads", "prerequisite": "Processes", "confidence": 0.8}
            ],
        }

    monkeypatch.setattr(ModelGateway, "generate_structured", infer)
    service = KnowledgeService(config, store)
    await index_all(service, course["id"])
    data = service.topics(course["id"])
    assert (
        len(data["prerequisites"]) == 1 and data["prerequisites"][0]["is_inferred"] == 1
    )
    link = data["prerequisites"][0]
    service.link_prerequisite(
        course["id"], link["topic_id"], link["prerequisite_topic_id"], 1, False
    )
    await index_all(service, course["id"])
    assert service.topics(course["id"])["prerequisites"][0]["is_inferred"] == 0
    other = store.create_course("Other", "")
    foreign = service.upsert_topic(other["id"], "Other topic")
    with pytest.raises(ValueError, match="this course"):
        service.link_prerequisite(course["id"], link["topic_id"], foreign["id"], 1)


@pytest.mark.asyncio
async def test_source_changed_during_embedding_never_publishes_stale_index(
    library, monkeypatch
):
    config, store, course, locations, _ = library
    config.openai_api_key = "fake"
    service = KnowledgeService(config, store)
    unit_id = locations[("textbook", "page:12")]
    with store.db._connect() as c:
        source_id = c.execute(
            "SELECT source_id FROM content_units WHERE id=?", (unit_id,)
        ).fetchone()[0]

    async def embed(self, texts):
        with store.db._connect() as c:
            c.execute("UPDATE content_units SET text='Changed' WHERE id=?", (unit_id,))
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(ModelGateway, "embed", embed)
    with pytest.raises(ValueError, match="changed"):
        await service.index_source(source_id)
    assert service.status(source_id)["status"] == "stale"
    assert not (await service.retrieve(course["id"], "process")).items


@pytest.mark.asyncio
async def test_source_deleted_during_semantic_query_is_not_returned(
    library, monkeypatch
):
    config, store, course, _, _ = library
    config.openai_api_key = "fake"
    monkeypatch.setattr(
        ModelGateway,
        "embed",
        AsyncMock(side_effect=lambda texts: [[1.0, 0.0] for _ in texts]),
    )
    service = KnowledgeService(config, store)
    await index_all(service, course["id"])

    async def embed(self, texts):
        with store.db._connect() as c:
            c.execute("DELETE FROM sources WHERE course_id=?", (course["id"],))
        return [[1.0, 0.0]]

    monkeypatch.setattr(ModelGateway, "embed", embed)
    assert not (await service.retrieve(course["id"], "mutex")).items
    with store.db._connect() as c:
        assert c.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0
        assert (
            c.execute(
                "SELECT count(*) FROM chunks_fts WHERE chunks_fts MATCH 'mutex'"
            ).fetchone()[0]
            == 0
        )


def test_retrieval_api_validates_course_and_query(tmp_path):
    app = create_app(Settings(_env_file=None, pocketta_data_dir=tmp_path))
    with TestClient(app) as client:
        course = client.post("/api/courses", json={"title": "OS"}).json()
        assert (
            client.post(
                "/api/courses/missing/retrieve", json={"query": "mutex"}
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/courses/{course['id']}/retrieve", json={"query": "   "}
            ).status_code
            == 422
        )
        result = client.post(
            f"/api/courses/{course['id']}/retrieve", json={"query": "mutex"}
        )
        assert result.status_code == 200 and result.json()["coverage"] == "unsupported"
        topic = client.post(
            f"/api/courses/{course['id']}/topics", json={"name": " Processes "}
        ).json()
        same = client.post(
            f"/api/courses/{course['id']}/topics", json={"name": "processes"}
        ).json()
        assert same["id"] == topic["id"]


@pytest.mark.asyncio
async def test_fixture_evaluation():
    result = await evaluate(False)
    assert result["source_location_hit_rate"] == 1
    assert result["unsupported_accuracy"] == 1


@pytest.mark.asyncio
async def test_index_cancellation_and_restart_recovery(library, monkeypatch):
    from backend.app.services.scheduler import CourseScheduler

    config, store, course, _, _ = library
    config.openai_api_key = "fake"
    entered = asyncio.Event()

    async def embed(self, texts):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ModelGateway, "embed", embed)
    scheduler = CourseScheduler(config)
    service = KnowledgeService(config, store, scheduler)
    source_id = store.sources(course["id"])[0]["id"]
    service.enqueue(source_id)
    with pytest.raises(ValueError, match="already processing"):
        service.enqueue(source_id)
    await scheduler.start()
    await asyncio.wait_for(entered.wait(), 1)
    scheduler.running = False
    await service.stop()
    assert service.status(source_id)["status"] == "queued"
    assert not service.pending and not scheduler.jobs
    config.openai_api_key = ""
    await service.start()
    await scheduler.start()
    for _ in range(100):
        if not scheduler.jobs:
            break
        await asyncio.sleep(0.001)
    assert not scheduler.jobs
    assert service.status(source_id)["status"] == "keyword_ready"
    await scheduler.stop()


@pytest.mark.asyncio
async def test_transcript_changes_invalidate_even_without_source_read(tmp_path):
    from backend.tests.test_processor import prepared_processor
    from backend.tests.test_models import transcript

    processor = prepared_processor(tmp_path)
    db = processor.database
    db.save_transcript("lecture", transcript())
    store = CourseStore(db)
    store.attach_lecture("lecture")
    store.sync_lecture_units("lecture")
    service = processor.knowledge
    await service.index_source("lecture")
    previous = service.status("lecture")
    assert previous["status"] == "keyword_ready"
    revised = transcript()
    revised.segments[0].text = "Revised semaphore evidence"
    db.replace_transcript_and_invalidate_pack("lecture", revised)
    assert service.status("lecture")["status"] == "stale"
    course_id = store.source("lecture")["course_id"]
    await service.index_source("lecture")
    found = await service.retrieve(course_id, "semaphore")
    assert found.items[0].source_version == 2
