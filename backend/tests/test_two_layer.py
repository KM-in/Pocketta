import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.courses import CourseStore
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.services.course_packs import (
    CoursePackService,
    PackOutline,
    PackSection,
    SectionVerdict,
    PackOverview,
)
from backend.app.services.gateway import ModelGateway
from backend.app.services.knowledge import KnowledgeService, chunk_text
from backend.app.services.scheduler import CourseScheduler
from backend.app.services.providers import RequestCoordinator
from backend.app.services.summary_index import RoutingSummary, VectorCache
from backend.app.tools.evaluate_retrieval import seed_fixture


@pytest.fixture
def library(tmp_path, monkeypatch):
    for name in (
        "EMBEDDING_API_KEY",
        "EMBEDDING_MODEL",
        "EMBEDDING_BASE_URL",
        "MODEL_PROVIDER",
        "CEREBRAS_API_KEY",
        "LM_STUDIO_MODEL_ID",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings(
        _env_file=None,
        pocketta_data_dir=tmp_path,
        model_provider="lm_studio",
        lm_studio_model_id="test",
        openai_api_key="",
        embedding_api_key="",
    )
    db = Database(settings.database_path)
    db.initialize()
    store = CourseStore(db)
    store.initialize()
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/knowledge/multi-source.json").read_text()
    )
    course, _ = seed_fixture(store, fixture)
    scheduler = CourseScheduler(settings)
    coordinator = RequestCoordinator(settings)
    knowledge = KnowledgeService(settings, store, scheduler, coordinator)
    packs = CoursePackService(settings, store, knowledge, scheduler, coordinator)
    calls = []

    async def generate(self, prompt, schema, **kwargs):
        data = json.loads(prompt.split("\n", 1)[1])
        calls.append((schema.__name__, kwargs.get("feature")))
        if schema is RoutingSummary:
            ids = (
                [r["chunk_id"] for r in data]
                if isinstance(data, list)
                else data["allowed_ids"]
            )
            return {
                "text": "Concurrency protects shared data from simultaneous mutation",
                "topics": ["Concurrency"],
                "supporting_chunk_ids": ids,
            }
        if schema is PackOutline:
            return {
                "topics": [
                    {
                        "title": "Concurrency",
                        "source_ids": [r["source_id"] for r in data],
                    }
                ]
            }
        if schema is PackSection:
            return {
                "supported": True,
                "title": "Concurrency",
                "items": [
                    {
                        "kind": "note",
                        "title": e["source_name"],
                        "text": e["excerpt"],
                        "chunk_ids": [e["chunk_id"]],
                        "options": [],
                        "correct_answer": None,
                    }
                    for e in data["original_evidence"]
                ],
            }
        if schema is SectionVerdict:
            return {
                "supported": True,
                "confidence": 0.99,
                "reason": "Supported by supplied excerpts",
            }
        if schema is PackOverview:
            return {
                "text": "This course covers mutual exclusion and waiting.",
                "chunk_ids": [data[0]["chunk_id"]],
            }
        raise AssertionError(schema)

    monkeypatch.setattr(ModelGateway, "generate_structured", generate)
    return settings, store, course, knowledge, packs, calls


async def index_all(library):
    _, store, course, knowledge, _, _ = library
    for source in store.sources(course["id"]):
        await knowledge.index_source(source["id"])


def test_paragraph_chunk_boundaries_preserve_offsets():
    text = "a word " * 20 + "\n\n" + "other word " * 50
    chunks = list(chunk_text(text, 200, 30))
    assert chunks[0][1] == text.index("\n\n")
    assert all(text[start:end] == value for start, end, value in chunks)
    assert chunks[-1][1] == len(text)


@pytest.mark.asyncio
async def test_summary_routing_selection_and_cached_generation(library):
    await index_all(library)
    _, store, course, knowledge, _, calls = library
    result = await knowledge.retrieve(course["id"], "simultaneous mutation")
    assert result.diagnostics["summary_matches"] > 0
    assert result.diagnostics["summary_routed_passages"] > 0
    assert {item.source_id for item in result.items} == {
        s["id"] for s in store.sources(course["id"])
    }
    source_id = store.sources(course["id"])[0]["id"]
    selected = await knowledge.retrieve(
        course["id"], "concurrency", source_ids=[source_id]
    )
    assert all(e.source_id == source_id for e in selected.items)
    before = len(calls)
    await knowledge.index_source(source_id)
    assert len(calls) == before
    assert knowledge.status(source_id)["summaries"]["status"] == "keyword_ready"
    with pytest.raises(ValueError, match="this course"):
        await knowledge.retrieve(course["id"], "mutex", source_ids=["foreign"])
    with store.db._connect() as c:
        c.execute(
            "UPDATE content_units SET text='Revised evidence' WHERE source_id=?",
            (source_id,),
        )
    assert knowledge.status(source_id)["summaries"]["status"] == "stale"


@pytest.mark.asyncio
async def test_invalid_summary_preserves_passage_search(library, monkeypatch):
    _, store, course, knowledge, _, _ = library
    monkeypatch.setattr(
        ModelGateway,
        "generate_structured",
        AsyncMock(
            return_value={
                "text": "Fake",
                "topics": [],
                "supporting_chunk_ids": ["invented"],
            }
        ),
    )
    await index_all(library)
    source = store.sources(course["id"])[0]
    assert knowledge.status(source["id"])["summaries"]["status"] == "failed"
    assert (await knowledge.retrieve(course["id"], "mutex")).items


@pytest.mark.asyncio
async def test_embedding_changes_rebuild_vectors_not_summaries(library, monkeypatch):
    await index_all(library)
    settings, store, course, knowledge, _, calls = library
    before = len(calls)
    settings.embedding_base_url = "http://localhost:1234/v1"
    settings.embedding_model = "local-embedding"
    embed = AsyncMock(side_effect=lambda texts: [[1.0, 0.0] for _ in texts])
    monkeypatch.setattr(ModelGateway, "embed", embed)
    for source in store.sources(course["id"]):
        await knowledge.index_source(source["id"])
    assert len(calls) == before
    source = store.sources(course["id"])[0]
    assert knowledge.status(source["id"])["summaries"]["status"] == "ready"
    assert knowledge.status(source["id"])["embeddings"]["status"] == "ready"
    assert (
        await knowledge.retrieve(course["id"], "protecting concurrent modification")
    ).retrieval_mode == "hybrid"
    settings.embedding_model = "different"
    result = await knowledge.retrieve(
        course["id"], "protecting concurrent modification"
    )
    assert result.retrieval_mode == "keyword"


def test_vector_cache_rejects_incompatible_dimensions():
    cache = VectorCache()
    rows = [{"id": "a", "embedding_model": "m", "embedding_json": "[1,0]"}]
    assert cache.score("course", rows, [1, 0], "m")["a"] == pytest.approx(1)
    with pytest.raises(ValueError, match="dimensions"):
        cache.score("course", rows, [1, 0, 0], "m")
    assert cache.score("other", rows, [1, 0], "other-model") == {}


@pytest.mark.asyncio
async def test_local_embeddings_without_key_and_legacy_fallback(tmp_path, monkeypatch):
    settings = Settings(
        _env_file=None,
        embedding_base_url="http://127.0.0.1:1234/v1",
        embedding_api_key="",
        embedding_model="local",
    )
    db = Database(tmp_path / "embedding.sqlite3")
    db.initialize()
    store = CourseStore(db)
    store.initialize()
    original = httpx.AsyncClient

    def handler(request):
        assert str(request.url) == "http://127.0.0.1:1234/v1/embeddings"
        assert "Authorization" not in request.headers
        assert json.loads(request.content)["model"] == "local"
        return httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]}
        )

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )
    assert await ModelGateway(settings, db).embed(["Synthetic text"]) == [[1.0, 0.0]]
    legacy = Settings(
        _env_file=None, openai_api_key="legacy", openai_embedding_model="old"
    )
    assert (
        legacy.effective_embedding_key == "legacy"
        and legacy.effective_embedding_model == "old"
    )


@pytest.mark.asyncio
async def test_course_pack_coverage_and_stale_snapshot(library):
    _, store, course, knowledge, packs, _ = library
    ids = [s["id"] for s in store.sources(course["id"])]
    pack = packs.create(course["id"], ids)
    await packs.process(course["id"], pack.id)
    result = packs.get(course["id"], pack.id)
    assert result.status == "completed" and result.progress == 100
    assert set(result.coverage["cited_sources"]) == set(ids)
    assert result.sections[0]["status"] == "validated"
    with store.db._connect() as c:
        c.execute("DELETE FROM sources WHERE id=?", (ids[0],))
    assert packs.get(course["id"], pack.id).status == "stale"
    with pytest.raises(ValueError, match="changed"):
        packs.retry(course["id"], pack.id)


@pytest.mark.asyncio
async def test_pack_retry_reuses_validated_sections(library, monkeypatch):
    _, store, course, _, packs, calls = library
    ids = [s["id"] for s in store.sources(course["id"])]
    original = ModelGateway.generate_structured
    fail = True

    async def generate(self, prompt, schema, **kwargs):
        if schema is PackOverview and fail:
            raise ValueError("Synthetic assembly failure")
        return await original(self, prompt, schema, **kwargs)

    monkeypatch.setattr(ModelGateway, "generate_structured", generate)
    pack = packs.create(course["id"], ids)
    await packs.run(course["id"], pack.id)
    assert packs.get(course["id"], pack.id).status == "failed"
    section_calls = sum(schema == "PackSection" for schema, _ in calls)
    await packs.scheduler.cancel(f"pack:{pack.id}")
    fail = False
    packs.retry(course["id"], pack.id)
    await packs.run(course["id"], pack.id)
    assert packs.get(course["id"], pack.id).status == "completed"
    assert sum(schema == "PackSection" for schema, _ in calls) == section_calls


@pytest.mark.asyncio
async def test_verifier_rejection_becomes_coverage_gap(library, monkeypatch):
    _, store, course, _, packs, _ = library
    original = ModelGateway.generate_structured

    async def reject(self, prompt, schema, **kwargs):
        if schema is SectionVerdict:
            return {
                "supported": False,
                "confidence": 0.99,
                "reason": "Conflicting claim not supported",
            }
        return await original(self, prompt, schema, **kwargs)

    monkeypatch.setattr(ModelGateway, "generate_structured", reject)
    pack = packs.create(course["id"], [s["id"] for s in store.sources(course["id"])])
    await packs.run(course["id"], pack.id)
    result = packs.get(course["id"], pack.id)
    assert result.sections[0]["status"] == "unsupported"
    assert not result.sections[0]["content"]["items"]
    assert len(result.coverage["omitted_sources"]) == 3


@pytest.mark.asyncio
async def test_pack_cancellation_and_restart(library, monkeypatch):
    _, store, course, _, packs, _ = library
    entered = asyncio.Event()

    async def waiting(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ModelGateway, "generate_structured", waiting)
    pack = packs.create(course["id"], [store.sources(course["id"])[0]["id"]])
    await packs.scheduler.start()
    await asyncio.wait_for(entered.wait(), 1)
    await packs.stop()
    assert packs.get(course["id"], pack.id).status == "queued"
    await packs.scheduler.stop()
    await packs.start()
    assert f"pack:{pack.id}" in packs.scheduler.jobs
    await packs.cancel(course["id"], pack.id)
    assert packs.get(course["id"], pack.id).status == "cancelled"


def test_course_pack_api_isolation_and_migration(tmp_path, monkeypatch):
    config = Settings(
        _env_file=None,
        pocketta_data_dir=tmp_path,
        model_provider="lm_studio",
        lm_studio_model_id="",
        embedding_api_key="",
        openai_api_key="",
    )
    app = create_app(config)
    monkeypatch.setattr(
        ModelGateway,
        "generate_structured",
        AsyncMock(side_effect=ValueError("Synthetic unavailable model")),
    )
    with TestClient(app) as client:
        store = app.state.courses
        fixture = json.loads(
            (Path(__file__).parent / "fixtures/knowledge/multi-source.json").read_text()
        )
        course, _ = seed_fixture(store, fixture)
        other = store.create_course("Other", "")
        source = store.sources(course["id"])[0]
        assert (
            client.post(
                f"/api/courses/{other['id']}/study-packs",
                json={"source_ids": [source["id"]]},
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/courses/{other['id']}/retrieve",
                json={"query": "mutex", "source_ids": [source["id"]]},
            ).status_code
            == 404
        )
        assert client.get(f"/api/courses/{course['id']}/study-packs").json() == []
        response = client.post(
            f"/api/courses/{course['id']}/study-packs",
            json={"source_ids": [source["id"]]},
        )
        assert response.status_code == 202 and response.json()["status"] == "queued"
        pack_id = response.json()["id"]
        assert (
            client.get(f"/api/courses/{course['id']}/study-packs/{pack_id}").status_code
            == 200
        )
        assert (
            client.get(f"/api/courses/{other['id']}/study-packs/{pack_id}").status_code
            == 404
        )
        store.initialize()
        store.initialize()
        assert len(store.sources(course["id"])) == 3


@pytest.mark.asyncio
async def test_source_edit_during_generation_never_publishes_section(
    library, monkeypatch
):
    _, store, course, _, packs, _ = library
    sid = store.sources(course["id"])[0]["id"]
    original = ModelGateway.generate_structured

    async def edit(self, prompt, schema, **kwargs):
        result = await original(self, prompt, schema, **kwargs)
        if schema is PackSection:
            with store.db._connect() as c:
                c.execute(
                    "UPDATE content_units SET text='New source version' WHERE source_id=?",
                    (sid,),
                )
        return result

    monkeypatch.setattr(ModelGateway, "generate_structured", edit)
    pack = packs.create(course["id"], [sid])
    await packs.run(course["id"], pack.id)
    result = packs.get(course["id"], pack.id)
    assert result.status == "stale" and not result.sections


@pytest.mark.asyncio
async def test_interrupted_summary_resumes_but_old_sources_do_not_backfill(
    library, monkeypatch
):
    _, store, course, knowledge, _, _ = library
    sid = store.sources(course["id"])[0]["id"]
    entered = asyncio.Event()

    async def waiting(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ModelGateway, "generate_structured", waiting)
    task = asyncio.create_task(knowledge.index_source(sid))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert knowledge.status(sid)["summaries"]["status"] == "queued"
    await knowledge.start()
    assert f"knowledge:{sid}" in knowledge.scheduler.jobs
    # Old sources without a summary-index row are only passage-indexed on startup.
    for source in store.sources(course["id"]):
        if source["id"] != sid:
            assert (
                knowledge.status(source["id"])["summaries"]["status"] == "not_indexed"
            )
    await knowledge.stop()


@pytest.mark.asyncio
async def test_summary_failure_during_source_change_excludes_old_routes(
    library, monkeypatch
):
    _, store, course, knowledge, _, _ = library
    sid = store.sources(course["id"])[0]["id"]
    original = ModelGateway.generate_structured

    async def edit(self, prompt, schema, **kwargs):
        result = await original(self, prompt, schema, **kwargs)
        with store.db._connect() as c:
            c.execute(
                "UPDATE content_units SET text='Changed before summary publication' WHERE source_id=?",
                (sid,),
            )
        return result

    monkeypatch.setattr(ModelGateway, "generate_structured", edit)
    await knowledge.index_source(sid)
    assert knowledge.summaries.rows(sid) == []
    assert (
        await knowledge.retrieve(course["id"], "concurrency", source_ids=[sid])
    ).items == []
