import json
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.courses import CourseStore
from backend.app.database import Database
from backend.app.main import create_app
from backend.app.services.generation import GenerationError
from backend.app.services.gateway import GradeResult
from backend.app.services.knowledge import KnowledgeService
from backend.app.services.tutor import TutorService
from backend.app.tools.evaluate_retrieval import FIXTURE, seed_fixture


@pytest.fixture
async def tutor(tmp_path):
    config = Settings(_env_file=None, pocketta_data_dir=tmp_path, openai_api_key="")
    db = Database(config.database_path)
    db.initialize()
    store = CourseStore(db)
    store.initialize()
    course, locations = seed_fixture(store, json.loads(FIXTURE.read_text()))
    knowledge = KnowledgeService(config, store)
    for source in store.sources(course["id"]):
        await knowledge.index_source(source["id"])
    service = TutorService(config, store, knowledge)
    bundle = await knowledge.retrieve(course["id"], "deadlock")
    item = bundle.items[0]
    draft = {
        "supported": True,
        "claims": [
            {
                "text": "Deadlock involves processes waiting forever for resources.",
                "chunk_ids": [item.chunk_id],
            }
        ],
        "check": None,
    }
    verdict = {
        "relevant": True,
        "claims": [
            {
                "claim_index": 0,
                "supported": True,
                "confidence": 0.95,
                "reason": "Explicit in the excerpt",
            }
        ],
        "check_supported": True,
        "check_unambiguous": True,
        "check_confidence": 0.95,
    }
    gateway = Mock(
        generate_structured=AsyncMock(side_effect=[draft, verdict]),
        grade_answer=AsyncMock(),
    )
    service.gateway_factory = Mock(return_value=gateway)
    return service, store, course["id"], item, draft, verdict, gateway, locations


@pytest.mark.asyncio
async def test_grounded_answer_separate_verifier_history_and_no_grade(tutor):
    service, store, course, item, draft, verdict, gateway, _ = tutor
    retrieve = service.knowledge.retrieve = AsyncMock(wraps=service.knowledge.retrieve)
    turn = await service.ask(course, "Explain deadlock", "explain")
    assert turn["status"] == "answered" and turn["claims"] == draft["claims"]
    assert turn["evidence"]["items"][0]["citation"]["page_no"] == 44
    assert (
        gateway.generate_structured.call_args_list[1].kwargs["role"] == "verification"
    )
    assert retrieve.await_count == 1
    assert turn["check"] is None and turn["grade"] is None
    restored = TutorService(None, store, service.knowledge).history(course)
    assert restored == [turn]
    from backend.app.services.quizzes import QuizService

    learning = QuizService(None, store, service.knowledge).learning(course)
    assert learning["conversation_interaction_count"] == 1
    assert learning["conversation_activity"]
    assert all(item["interaction_count"] == 1 for item in learning["conversation_activity"])
    assert all(item["last_signal"] == "conversation" for item in learning["conversation_activity"])
    assert learning["topics"] == []  # Discussion activity is not mastery evidence.
    assert service.history(store.create_course("Other", "")["id"]) == []
    with pytest.raises(ValueError, match="no unanswered"):
        await service.answer_check(course, turn["id"], "some answer")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["unsupported", "low_confidence", "missing_verdict", "irrelevant"]
)
async def test_real_citation_does_not_prove_support(tutor, mutation):
    service, _, course, _, draft, verdict, gateway, _ = tutor
    draft["claims"][0]["text"] = "Deadlock guarantees unlimited throughput."
    if mutation == "unsupported":
        verdict["claims"][0]["supported"] = False
    if mutation == "low_confidence":
        verdict["claims"][0]["confidence"] = 0.4
    if mutation == "missing_verdict":
        verdict["claims"] = []
    if mutation == "irrelevant":
        verdict["relevant"] = False
    turn = await service.ask(course, "Explain deadlock", "explain")
    assert (
        turn["status"] == "unsupported"
        and not turn["claims"]
        and not turn["evidence"]["items"]
    )


@pytest.mark.asyncio
async def test_no_evidence_refuses_without_model(tutor):
    service, _, course, _, _, _, gateway, _ = tutor
    turn = await service.ask(course, "photosynthesis chloroplasts", "explain")
    assert turn["status"] == "unsupported"
    gateway.generate_structured.assert_not_called()
    assert service.history(course)[0]["question"] == "photosynthesis chloroplasts"


@pytest.mark.asyncio
async def test_foreign_or_invented_citation_rejected(tutor):
    service, _, course, _, draft, _, gateway, _ = tutor
    draft["claims"][0]["chunk_ids"] = ["another-course-chunk"]
    with pytest.raises(ValueError, match="outside"):
        await service.ask(course, "Explain deadlock", "explain")
    assert gateway.generate_structured.await_count == 1
    assert service.history(course) == []


@pytest.mark.asyncio
async def test_verifier_failure_publishes_nothing(tutor):
    service, _, course, _, draft, _, gateway, _ = tutor
    gateway.generate_structured.side_effect = [draft, GenerationError("offline")]
    with pytest.raises(GenerationError):
        await service.ask(course, "Explain deadlock", "explain")
    assert service.history(course) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["edit", "delete", "uncertain", "move"])
async def test_changed_evidence_during_verification_is_not_published(tutor, change):
    service, store, course, item, draft, verdict, gateway, _ = tutor

    async def generate(prompt, schema, **kwargs):
        if kwargs.get("role") == "verification":
            with store.db._connect() as c:
                if change == "edit":
                    c.execute(
                        "UPDATE content_units SET text='changed' WHERE id=?",
                        (item.content_unit_id,),
                    )
                if change == "delete":
                    c.execute("DELETE FROM sources WHERE id=?", (item.source_id,))
                if change == "uncertain":
                    c.execute(
                        "UPDATE content_units SET uncertain=1 WHERE id=?",
                        (item.content_unit_id,),
                    )
                if change == "move":
                    c.execute(
                        "UPDATE sources SET course_id=? WHERE id=?",
                        (store.create_course("Other", "")["id"], item.source_id),
                    )
            return verdict
        return draft

    gateway.generate_structured.side_effect = generate
    with pytest.raises(ValueError, match="evidence changed"):
        await service.ask(course, "Explain deadlock", "explain")
    assert service.history(course) == []


@pytest.mark.asyncio
async def test_explicit_check_private_rubric_persistent_grade_and_one_submission(tutor):
    service, store, course, item, draft, verdict, gateway, _ = tutor
    draft["claims"] = []
    draft["check"] = {
        "question": "Name the four deadlock conditions.",
        "expected_answer": "Mutual exclusion, hold and wait, no preemption, circular wait.",
        "rubric": "One quarter for each condition.",
        "chunk_ids": [item.chunk_id],
    }
    verdict["claims"] = []
    turn = await service.ask(course, "Test my understanding of deadlock", "check")
    assert turn["status"] == "answered" and turn["check"]
    assert "expected_answer" not in turn["check"] and "rubric" not in turn["check"]
    gateway.grade_answer.return_value = GradeResult(
        score=0.5,
        confidence=0.6,
        feedback="Two conditions identified.",
        uncertain=False,
        content_unit_ids=[item.content_unit_id],
    )
    other = store.create_course("Other", "")["id"]
    with pytest.raises(LookupError):
        await service.answer_check(other, turn["id"], "answer")
    answered = await service.answer_check(
        course, turn["id"], "mutual exclusion and circular wait"
    )
    assert (
        answered["grade"]["uncertain"]
        and answered["response"]
        and answered["answered_at"]
    )
    grading_input = gateway.grade_answer.call_args.args[0]
    assert item.excerpt == grading_input.evidence[0].text
    assert "One quarter" in grading_input.rubric
    assert service.history(course)[0] == answered
    from backend.app.services.quizzes import QuizService

    activity = QuizService(None, store, service.knowledge).learning(course)["conversation_activity"]
    assert activity and all(item["last_signal"] == "graded_check" for item in activity)
    with pytest.raises(ValueError, match="no unanswered"):
        await service.answer_check(course, turn["id"], "retry")


@pytest.mark.asyncio
async def test_ambiguous_check_refused_and_ordinary_chat_cannot_create_check(tutor):
    service, _, course, item, draft, verdict, _, _ = tutor
    draft["check"] = {
        "question": "Explain everything",
        "expected_answer": "Everything",
        "rubric": "All correct",
        "chunk_ids": [item.chunk_id],
    }
    with pytest.raises(ValueError, match="invalid understanding check"):
        await service.ask(course, "Explain deadlock", "explain")
    verdict["check_unambiguous"] = False
    service.gateway_factory.return_value.generate_structured.side_effect = [
        draft,
        verdict,
    ]
    turn = await service.ask(course, "Test deadlock", "check")
    assert turn["status"] == "unsupported" and turn["check"] is None


def test_tutor_api_validation_history_and_scoped_citations(tmp_path):
    app = create_app(
        Settings(_env_file=None, pocketta_data_dir=tmp_path, openai_api_key="")
    )
    with TestClient(app) as client:
        course, locations = seed_fixture(
            app.state.courses, json.loads(FIXTURE.read_text())
        )
        path = f'/api/courses/{course["id"]}'
        assert client.post(path + "/tutor", json={"question": " "}).status_code == 422
        assert (
            client.post(
                path + "/tutor", json={"question": "abc", "intent": "invalid"}
            ).status_code
            == 422
        )
        assert (
            client.post(path + "/tutor", json={"question": "photosynthesis"}).json()[
                "status"
            ]
            == "unsupported"
        )
        assert len(client.get(path + "/tutor").json()) == 1
        assert client.get("/api/courses/missing/tutor").status_code == 404
        unit = locations[("lecture", "time:62000-79000:seg-0004")]
        citation = client.get(path + f"/citations/{unit}?version=1").json()
        assert citation["start_sec"] == 62 and citation["end_sec"] == 79
        other = app.state.courses.create_course("Other", "")["id"]
        assert client.get(f"/api/courses/{other}/citations/{unit}").status_code == 404
        assert client.get(path + f"/citations/{unit}?version=99").status_code == 409
        uncertain = locations[("textbook", "page:99")]
        assert client.get(path + f"/citations/{uncertain}").status_code == 409
        app.state.tutor.ask = AsyncMock(side_effect=GenerationError("offline"))
        assert (
            client.post(path + "/tutor", json={"question": "deadlock"}).status_code
            == 503
        )
