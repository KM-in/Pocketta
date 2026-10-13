import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from backend.app.config import Settings
from backend.app.courses import CourseStore
from backend.app.database import Database
from backend.app.services.gateway import ModelGateway, GradingInput
from backend.app.services.generation import GenerationError
from backend.app.services.providers import RequestCoordinator, text_adapter
from backend.app.services.scheduler import CourseScheduler
from backend.tests.test_models import transcript, study_pack


@pytest.fixture
def store(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.initialize()
    store = CourseStore(db)
    store.initialize()
    return store


def transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def settings(**kwargs):
    return Settings(_env_file=None, **kwargs)


class Result(BaseModel):
    answer: str


def test_cloud_endpoint_defaults_and_environment(monkeypatch):
    adapter = text_adapter(settings(model_provider="cerebras"))
    assert adapter.base_url == "https://api.cerebras.ai/v1"
    assert adapter.completion_token_field == "max_completion_tokens"
    monkeypatch.setenv("CEREBRAS_BASE_URL", " https://inference.example/api/v2/// ")
    monkeypatch.setenv("CEREBRAS_COMPLETION_TOKEN_FIELD", "max_tokens")
    adapter = text_adapter(settings(model_provider="cerebras"))
    assert adapter.base_url == "https://inference.example/api/v2"
    assert adapter.completion_token_field == "max_tokens"


def test_cloud_reasoning_defaults_are_overridable():
    config = settings(model_provider="cerebras")
    adapter = text_adapter(config)
    payload = {"model": "qwen-3.8-27b", "max_tokens": 900}
    assert adapter.chat_payload(payload)["reasoning_effort"] == "medium"
    assert "reasoning_effort" not in payload
    assert adapter.chat_payload(
        {**payload, "model": "other-model"}
    )["reasoning_effort"] == "medium"
    assert adapter.chat_payload(
        {**payload, "reasoning_effort": "low"}
    )["reasoning_effort"] == "low"

    config.cerebras_base_url = "https://inference.example/v1"
    assert text_adapter(config).chat_payload(payload)["reasoning_effort"] == "medium"
    config.cerebras_reasoning_effort = ""
    assert "reasoning_effort" not in text_adapter(config).chat_payload(payload)
    config.cerebras_reasoning_effort = "high"
    adapter = text_adapter(config)
    assert adapter.chat_payload(payload)["reasoning_effort"] == "high"
    assert adapter.chat_payload({**payload, "model": "verifier"})[
        "reasoning_effort"
    ] == "high"


def test_cloud_reasoning_effort_from_environment(monkeypatch):
    monkeypatch.setenv("CEREBRAS_REASONING_EFFORT", "low")
    config = settings(model_provider="cerebras")
    assert text_adapter(config).chat_payload({"model": "qwen-3.8-27b"})[
        "reasoning_effort"
    ] == "low"


@pytest.mark.parametrize("content", [None, '{"answer":"partial'])
@pytest.mark.parametrize("limit", [900, 4096, 72_000])
@pytest.mark.asyncio
async def test_output_limit_is_actionable_and_preserves_billable_usage(
    store, monkeypatch, content, limit
):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [{
                    "finish_reason": "length",
                    "message": {"content": content, "reasoning": "private reasoning"},
                }],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": limit,
                    "completion_tokens_details": {"reasoning_tokens": limit},
                },
            },
        )

    transport(monkeypatch, handler)
    gateway = ModelGateway(
        settings(model_provider="cerebras", cerebras_api_key="secret"), store.db
    )
    with pytest.raises(GenerationError, match=f"output token limit \\({limit}\\)") as error:
        await gateway._generate_model(Result, "Prompt", max_tokens=limit)
    assert "Reduce reasoning effort" in str(error.value)
    assert "private reasoning" not in str(error.value)
    assert "secret" not in str(error.value)
    assert len(requests) == 1
    assert json.loads(requests[0].content)["reasoning_effort"] == "medium"
    with store.db._connect() as c:
        row = dict(c.execute("SELECT * FROM model_runs").fetchone())
    assert row["status"] == "failed" and row["attempts"] == 1
    assert json.loads(row["usage_json"])["completion_tokens"] == limit


@pytest.mark.parametrize(
    "url",
    [
        "",
        "inference.example/v1",
        "ftp://inference.example/v1",
        "https:///v1",
        "https://user:secret@inference.example/v1",
        "https://inference.example/v1?key=secret",
        "https://inference.example/v1#fragment",
    ],
)
def test_cloud_endpoint_rejects_invalid_base_urls(url):
    with pytest.raises(ValidationError, match="Cloud base URL"):
        settings(cerebras_base_url=url)


@pytest.mark.parametrize("token_field", ["max_tokens", "max_completion_tokens"])
@pytest.mark.asyncio
async def test_custom_cloud_endpoint_for_models_text_roles_and_vision(
    store, monkeypatch, tmp_path, token_field
):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer custom-key"
        if request.method == "GET":
            return httpx.Response(200, json={"data": [{"id": "custom-text"}]})
        payload = json.loads(request.content)
        assert payload[token_field] == 72_000
        other_field = (
            "max_tokens"
            if token_field == "max_completion_tokens"
            else "max_completion_tokens"
        )
        assert other_field not in payload
        assert payload["response_format"]["type"] == "json_schema"
        result = (
            {"transcription": "Text", "description": "Diagram", "uncertain": False}
            if payload["model"] == "custom-vision"
            else {"answer": "Generated"}
        )
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(result)}}]}
        )

    transport(monkeypatch, handler)
    gateway = ModelGateway(
        settings(
            model_provider="cerebras",
            cerebras_base_url="https://inference.example/api/v2/",
            cerebras_api_key="custom-key",
            cerebras_text_model="custom-text",
            cerebras_vision_model="custom-vision",
            cerebras_completion_token_field=token_field,
            verifier_model="custom-verifier",
            grader_model="custom-grader",
        ),
        store.db,
    )
    assert await gateway.available_models() == ["custom-text"]
    for role in ("generation", "verification", "grading"):
        assert await gateway.generate_structured("Prompt", Result, role=role) == {
            "answer": "Generated"
        }
    image = tmp_path / "page.png"
    image.write_bytes(b"test-image")
    assert (await gateway.analyse_image(image, "Read this")).description == "Diagram"
    assert [str(request.url) for request in requests] == [
        "https://inference.example/api/v2/models",
        *["https://inference.example/api/v2/chat/completions"] * 4,
    ]
    assert [json.loads(request.content)["model"] for request in requests[1:]] == [
        "custom-text",
        "custom-verifier",
        "custom-grader",
        "custom-vision",
    ]
    vision_payload = json.loads(requests[-1].content)
    assert vision_payload["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


def test_settings_legacy_alias_and_neutral_precedence():
    config = settings(lm_studio_chunk_chars=3000, lm_studio_timeout_seconds=12)
    assert (
        config.generation_chunk_chars == 3000
        and config.generation_timeout_seconds == 12
    )
    assert (
        settings(
            lm_studio_chunk_chars=3000, generation_chunk_chars=4000
        ).generation_chunk_chars
        == 4000
    )
    with pytest.raises(ValidationError):
        settings(job_concurrency=0)
    with pytest.raises(ValidationError):
        settings(model_token_rates={"openai/test": {"input": -1}})


def test_existing_model_runs_migration_is_idempotent(store):
    with store.db._connect() as c:
        c.execute("DROP TABLE model_runs")
        c.execute(
            "CREATE TABLE model_runs (id TEXT PRIMARY KEY, source_id TEXT, provider TEXT, model TEXT, feature TEXT, prompt_version TEXT, latency REAL, usage_json TEXT, status TEXT, created_at TEXT)"
        )
        c.execute(
            "INSERT INTO model_runs(id,provider,status) VALUES ('old','cerebras','completed')"
        )
    store.initialize()
    store.initialize()
    with store.db._connect() as c:
        row = dict(c.execute("SELECT * FROM model_runs WHERE id='old'").fetchone())
    assert row["attempts"] == 1 and row["estimated_cost_usd"] is None


@pytest.mark.asyncio
async def test_openai_embedding_order_usage_and_cost(store, monkeypatch):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.3, 0.4]},
                    {"index": 0, "embedding": [0.1, 0.2]},
                ],
                "usage": {"prompt_tokens": 100, "total_tokens": 100},
            },
        )

    transport(monkeypatch, handler)
    gateway = ModelGateway(
        settings(
            openai_api_key="secret",
            model_token_rates={"openai/text-embedding-3-small": {"input": 2}},
        ),
        store.db,
    )
    assert await gateway.embed(["first", "second"]) == [[0.1, 0.2], [0.3, 0.4]]
    assert requests[0].url == "https://api.openai.com/v1/embeddings"
    with store.db._connect() as c:
        row = dict(c.execute("SELECT * FROM model_runs").fetchone())
    assert row["estimated_cost_usd"] == pytest.approx(0.0002)
    assert row["validation_status"] == "valid" and "secret" not in json.dumps(row)
    assert await gateway.embed([]) == []
    with pytest.raises(ValueError, match="nonblank"):
        await gateway.embed([""])


@pytest.mark.parametrize(
    "data",
    [
        [],
        [{"index": 1, "embedding": [1]}],
        [{"index": 0, "embedding": []}],
        [{"index": 0, "embedding": [True]}],
        [{"index": 0, "embedding": ["bad"]}],
    ],
)
@pytest.mark.asyncio
async def test_embedding_rejects_invalid_vectors(store, monkeypatch, data):
    transport(monkeypatch, lambda request: httpx.Response(200, json={"data": data}))
    gateway = ModelGateway(settings(openai_api_key="secret"), store.db)
    with pytest.raises(ValueError, match="Invalid embedding"):
        await gateway.embed(["text"])
    with store.db._connect() as c:
        assert (
            c.execute("SELECT validation_status FROM model_runs").fetchone()[0]
            == "invalid"
        )


@pytest.mark.asyncio
async def test_model_roles_and_grading_citation_validation(store, monkeypatch):
    models = []

    def handler(request):
        payload = json.loads(request.content)
        models.append(payload["model"])
        if payload["model"] == "grade":
            result = {
                "score": 0.75,
                "confidence": 0.8,
                "feedback": "Mostly correct",
                "uncertain": False,
                "content_unit_ids": ["wrong" if len(models) == 2 else "unit"],
            }
        else:
            result = {"answer": "verified"}
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(result)}}]}
        )

    transport(monkeypatch, handler)
    gateway = ModelGateway(
        settings(
            model_provider="cerebras",
            cerebras_api_key="secret",
            verifier_model="verify",
            grader_model="grade",
        ),
        store.db,
    )
    assert await gateway.generate_structured("Check", Result, role="verification") == {
        "answer": "verified"
    }
    result = await gateway.grade_answer(
        GradingInput(
            question="Explain",
            rubric="Correct definition",
            response="Answer",
            evidence=[{"content_unit_id": "unit", "text": "Definition"}],
        )
    )
    assert result.score == 0.75
    assert models == ["verify", "grade", "grade"]
    with store.db._connect() as c:
        rows = c.execute(
            "SELECT validation_status FROM model_runs ORDER BY rowid"
        ).fetchall()
    assert [row[0] for row in rows] == ["valid", "invalid", "valid"]
    assert gateway.text_model == gateway.settings.cerebras_text_model


@pytest.mark.asyncio
async def test_grading_rejects_persistent_invalid_score(store):
    gateway = ModelGateway(settings(lm_studio_model_id="local"), store.db)
    gateway._complete = AsyncMock(
        return_value=json.dumps(
            {
                "score": 2,
                "confidence": 0.5,
                "feedback": "bad",
                "uncertain": False,
                "content_unit_ids": [],
            }
        )
    )
    with pytest.raises(GenerationError, match="Invalid structured"):
        await gateway.grade_answer(
            GradingInput(
                question="Q",
                rubric="R",
                response="",
                evidence=[{"content_unit_id": "u", "text": "E"}],
            )
        )


@pytest.mark.asyncio
async def test_local_usage_estimate_and_no_api_cost(store, monkeypatch):
    transport(
        monkeypatch,
        lambda request: httpx.Response(
            200, json={"choices": [{"message": {"content": '{"answer":"yes"}'}}]}
        ),
    )
    gateway = ModelGateway(settings(lm_studio_model_id="local"), store.db)
    await gateway.generate_structured("Prompt", Result)
    with store.db._connect() as c:
        row = dict(c.execute("SELECT * FROM model_runs").fetchone())
    assert row["estimated_cost_usd"] == 0
    usage = json.loads(row["usage_json"])
    assert (
        usage["usage_source"] == "character_estimate"
        and usage["estimated_input_tokens"] > 0
    )


@pytest.mark.asyncio
async def test_shared_gateway_concurrent_sources_are_attributed(
    store, monkeypatch, tmp_path
):
    course = store.create_course("Course", "")
    for id in ("a", "b"):
        with store.db._connect() as c:
            c.execute(
                "INSERT INTO sources(id,course_id,name,type,file_path,status,created_at) VALUES (?,?,?,'recording','','ready','now')",
                (id, course["id"], id),
            )

    async def handler(request):
        await asyncio.sleep(0)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": study_pack().model_dump_json()}}]
            },
        )

    transport(monkeypatch, handler)
    gateway = ModelGateway(settings(lm_studio_model_id="local"), store.db)
    await asyncio.gather(
        *(gateway.generate(transcript(), source_id=id) for id in ("a", "b"))
    )
    with store.db._connect() as c:
        rows = c.execute(
            "SELECT source_id,course_id,validation_status FROM model_runs"
        ).fetchall()
    assert {row["source_id"] for row in rows} == {"a", "b"}
    assert all(
        row["course_id"] == course["id"] and row["validation_status"] == "valid"
        for row in rows
    )


@pytest.mark.asyncio
async def test_transport_retries_and_sanitizes_failures(store, monkeypatch):
    count = 0

    def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(
            429, headers={"Retry-After": "0"}, text="secret prompt key"
        )

    transport(monkeypatch, handler)
    gateway = ModelGateway(settings(openai_api_key="secret"), store.db)
    with pytest.raises(GenerationError) as error:
        await gateway.embed(["private material"])
    assert "secret" not in str(error.value) and count == 3
    with store.db._connect() as c:
        row = dict(c.execute("SELECT * FROM model_runs").fetchone())
    assert (
        row["attempts"] == 3
        and row["status"] == "failed"
        and row["estimated_cost_usd"] is None
    )


@pytest.mark.asyncio
async def test_cancelled_request_records_outcome_and_releases_slot(store, monkeypatch):
    entered = asyncio.Event()

    async def handler(request):
        entered.set()
        await asyncio.Event().wait()

    transport(monkeypatch, handler)
    config = settings(openai_api_key="secret")
    coordinator = RequestCoordinator(config)
    gateway = ModelGateway(config, store.db, coordinator=coordinator)
    task = asyncio.create_task(gateway.embed(["text"]))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with asyncio.timeout(1):
        async with coordinator.slot("openai"):
            pass
    with store.db._connect() as c:
        assert c.execute("SELECT status FROM model_runs").fetchone()[0] == "cancelled"


@pytest.mark.asyncio
async def test_scheduler_course_fifo_fairness_and_queued_cancellation():
    scheduler = CourseScheduler(settings(job_concurrency=2))
    release = {id: asyncio.Event() for id in ["a1", "a2", "b1", "c1"]}
    started, completed = [], []

    async def run(id):
        started.append(id)
        await release[id].wait()

    for id in ["a1", "a2", "b1", "c1"]:
        scheduler.submit(
            id, id[0], lambda id=id: run(id), lambda id=id: completed.append(id)
        )
    with pytest.raises(ValueError):
        scheduler.submit("a1", "a", lambda: run("a1"), lambda: None)
    await scheduler.start()
    await asyncio.sleep(0)
    assert started == ["a1", "b1"]
    await scheduler.cancel("a2")
    release["a1"].set()
    for _ in range(4):
        await asyncio.sleep(0)
    assert started == ["a1", "b1", "c1"] and "a2" in completed
    await scheduler.stop()
    assert not scheduler.jobs and not scheduler.active
    assert sorted(completed) == ["a1", "a2", "b1", "c1"]


@pytest.mark.asyncio
async def test_shared_provider_cooldown_and_concurrency(monkeypatch):
    from backend.app.services import providers

    clock = [10.0]
    sleeps = []

    async def sleep(delay):
        sleeps.append(delay)
        clock[0] += delay

    monkeypatch.setattr(providers.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(providers.asyncio, "sleep", sleep)
    coordinator = RequestCoordinator(settings(provider_request_interval_seconds=1))
    async with coordinator.slot("cerebras"):
        coordinator.cooldown("cerebras", "5", 1)
    async with coordinator.slot("cerebras"):
        pass
    assert sleeps == [5]
    async with coordinator.slot("openai"):
        pass
    assert sleeps == [5]


@pytest.mark.asyncio
async def test_recording_delete_waits_for_native_cleanup(tmp_path):
    import threading
    from backend.tests.test_processor import prepared_processor

    entered, release = threading.Event(), threading.Event()
    processor = prepared_processor(tmp_path)

    def normalize(*args):
        entered.set()
        release.wait(3)
        return 1000

    processor.media.normalize = normalize
    await processor.start()  # Recovers the queued recording.
    assert await asyncio.to_thread(entered.wait, 1)
    deleting = asyncio.create_task(processor.delete("lecture"))
    await asyncio.sleep(0.01)
    assert not deleting.done()
    release.set()
    assert await deleting
    await processor.queue.join()
    assert processor.database.get_lecture("lecture") is None
    await processor.stop()


@pytest.mark.asyncio
async def test_recording_and_document_share_scheduler_and_recover(
    tmp_path, monkeypatch
):
    from backend.app.main import create_app
    from backend.app.models import LectureStatus
    from backend.tests.test_courses import add_document

    app = create_app(settings(pocketta_data_dir=tmp_path, job_concurrency=2))
    app.state.settings.prepare_directories()
    app.state.database.initialize()
    app.state.courses.initialize()
    store = app.state.courses
    document_id, _ = add_document(store, tmp_path)
    with store.db._connect() as c:
        course_id = c.execute(
            "SELECT course_id FROM sources WHERE id=?", (document_id,)
        ).fetchone()[0]
    lecture_dir = app.state.settings.lectures_dir / "recording"
    lecture_dir.mkdir()
    source = lecture_dir / "source.mp3"
    source.write_bytes(b"audio")
    app.state.database.create_lecture("recording", "Lecture", source)
    app.state.courses.attach_lecture("recording", course_id)
    other = store.create_course("Other", "")
    other_id, _ = add_document(store, tmp_path)
    with store.db._connect() as c:
        c.execute("UPDATE sources SET course_id=? WHERE id=?", (other["id"], other_id))
    started = []
    release = asyncio.Event()

    async def document(id, generation_only):
        started.append(id)
        await release.wait()
        store.update(id, "ready", 100)

    async def recording(item):
        started.append(item.lecture_id)
        await release.wait()
        app.state.database.update_status(
            item.lecture_id, LectureStatus.COMPLETED, progress=100
        )

    monkeypatch.setattr(app.state.documents, "process", document)
    monkeypatch.setattr(app.state.processor, "_process", recording)
    async with app.router.lifespan_context(app):
        for _ in range(4):
            await asyncio.sleep(0)
        # Recording and document from the same course cannot run together.
        assert len(started) == 2 and other_id in started
        assert not {document_id, "recording"}.issubset(started)
        release.set()
        await asyncio.wait_for(
            asyncio.gather(
                app.state.documents.queue.join(), app.state.processor.queue.join()
            ),
            1,
        )
        assert set(started) == {document_id, "recording", other_id}
    assert store.source(document_id)["status"] == "ready"


@pytest.mark.asyncio
async def test_non_transient_errors_do_not_retry_and_malformed_body_is_safe(
    store, monkeypatch
):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(401, text="private response")
        return httpx.Response(200, json=["invalid body"])

    transport(monkeypatch, handler)
    gateway = ModelGateway(settings(openai_api_key="secret"), store.db)
    with pytest.raises(GenerationError, match="HTTP 401"):
        await gateway.embed(["text"])
    assert len(calls) == 1
    with pytest.raises(GenerationError, match="provider response"):
        await gateway.embed(["text"])
    assert len(calls) == 2
    with store.db._connect() as c:
        rows = c.execute(
            "SELECT attempts,status FROM model_runs ORDER BY rowid"
        ).fetchall()
    assert [(row[0], row[1]) for row in rows] == [(1, "failed"), (1, "failed")]
