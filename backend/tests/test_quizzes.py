import json
from unittest.mock import AsyncMock

import pytest

from backend.app.services.gateway import GradeResult, ModelGateway
from backend.app.services.quizzes import QuizDraft, QuizService, QuizVerification
from backend.tests.test_two_layer import index_all
from backend.tests.test_two_layer import library as base_library_fixture


@pytest.fixture
def library(tmp_path, monkeypatch):
    return base_library_fixture.__wrapped__(tmp_path, monkeypatch)


@pytest.mark.asyncio
async def test_assessment_review_falls_back_without_configured_model(library):
    settings, store, course, knowledge, _, _ = library
    settings.lm_studio_model_id = ""
    service = QuizService(settings, store, knowledge)

    report = await service._assessment_report(
        course["id"],
        [{"id": "q1", "topic": "Processes", "prompt": "What is a process?", "answer": "A running program", "explanation": "The cited distinction", "chunk_ids": []}],
        {"q1": "A program file"},
        {"q1": {"score": 0.0, "uncertain": False, "feedback": "Review the distinction"}},
        {},
    )

    assert report["weak_topics"] == ["Processes"]
    assert report["likely_misconceptions"] == []
    assert "No assessment-review model is configured" in report["summary"]


@pytest.mark.asyncio
async def test_one_quiz_mixes_sources_and_hides_answers_until_submission(
    library, monkeypatch
):
    settings, store, course, knowledge, _, _ = library
    await index_all(library)
    service = QuizService(settings, store, knowledge)
    draft = None

    async def generate(self, prompt, schema, **kwargs):
        nonlocal draft
        if schema is QuizDraft:
            evidence = json.loads(prompt.split("Evidence: ", 1)[1])
            by_source = {}
            for item in evidence:
                by_source.setdefault(item["source_id"], item)
            picks = list(by_source.values())[:2]
            assert len(picks) == 2
            draft = {
                "title": "Mixed concurrency quiz",
                "questions": [
                    {
                        "kind": "mcq",
                        "topic": "Concurrency",
                        "prompt": "Which statement is supported?",
                        "options": ["A", "B", "C", "D"],
                        "answer": "A",
                        "rubric": "Choose A.",
                        "explanation": "Evidence supports A.",
                        "chunk_ids": [picks[0]["chunk_id"]],
                    },
                    {
                        "kind": "short_answer",
                        "topic": "Concurrency",
                        "prompt": "Explain the source comparison.",
                        "options": [],
                        "answer": "Compare the cited claims.",
                        "rubric": "Compare claims using evidence.",
                        "explanation": "The sources describe concurrency behavior.",
                        "chunk_ids": [picks[1]["chunk_id"]],
                    },
                ],
            }
            return draft
        if schema is QuizVerification:
            return {
                "supported_question_indexes": [0, 1],
                "confidence": 0.99,
                "reason": "Verified",
            }
        raise AssertionError(schema)

    monkeypatch.setattr(ModelGateway, "generate_structured", generate)
    monkeypatch.setattr(
        ModelGateway,
        "grade_answer",
        AsyncMock(
            return_value=GradeResult(
                score=1,
                confidence=0.99,
                feedback="Supported answer.",
                uncertain=False,
                content_unit_ids=[],
            )
        ),
    )
    quiz = await service.generate(
        course["id"],
        [s["id"] for s in store.sources(course["id"])],
        question_count=2,
        mcq_count=1,
        fixed_topics=["Concurrency"],
    )
    assert len(quiz["questions"]) == 2
    assert "answer" not in quiz["questions"][0]
    with store.db._connect() as c:
        saved_questions = json.loads(
            c.execute(
                "SELECT questions_json FROM course_quizzes WHERE id=?", (quiz["id"],)
            ).fetchone()[0]
        )
    assert len({sid for q in saved_questions for sid in q["source_ids"]}) >= 2
    attempt = service.create_attempt(course["id"], quiz["id"])
    saved = service.save_answers(
        course["id"],
        attempt["id"],
        {
            quiz["questions"][0]["id"]: "A",
            quiz["questions"][1]["id"]: "A reasoned answer",
        },
    )
    assert "answer" not in saved["questions"][0]
    result = await service.submit(course["id"], attempt["id"])
    assert result["status"] == "completed"
    completed_quiz = service.get_quiz(course["id"], quiz["id"])
    assert completed_quiz["questions"][0]["answer"] == "A"
    assert completed_quiz["attempts"][0]["grades"]
    report = service.report_path(course["id"])
    assert report.exists() and "Mixed concurrency quiz" in report.read_text(
        encoding="utf-8"
    )
    retake = service.create_attempt(course["id"], quiz["id"])
    service.save_answers(
        course["id"],
        retake["id"],
        {
            quiz["questions"][0]["id"]: "A",
            quiz["questions"][1]["id"]: "A reasoned answer",
        },
    )
    grader = AsyncMock(
        side_effect=[
            RuntimeError("temporary grader failure"),
            GradeResult(
                score=1,
                confidence=0.99,
                feedback="Supported answer.",
                uncertain=False,
                content_unit_ids=[],
            ),
        ]
    )
    monkeypatch.setattr(ModelGateway, "grade_answer", grader)
    with pytest.raises(RuntimeError, match="temporary"):
        await service.submit(course["id"], retake["id"])
    partial = service.attempt(course["id"], retake["id"])
    assert partial["status"] == "grading" and partial["grade_count"] == 1
    assert (await service.submit(course["id"], retake["id"]))["status"] == "completed"
    assert grader.await_count == 2
    with store.db._connect() as c:
        assert (
            c.execute(
                "SELECT COUNT(*) FROM topic_observations WHERE course_id=?",
                (course["id"],),
            ).fetchone()[0]
            == 4
        )
    assert not service._profile(course["id"])[0]["mastered"]


@pytest.mark.asyncio
async def test_syllabus_mapping_and_studied_dimension_are_separate(library):
    settings, store, course, knowledge, _, _ = library
    await index_all(library)
    service = QuizService(settings, store, knowledge)
    syllabus = await service.save_syllabus(course["id"], "# Mutexes\n- Busy waiting")
    assert len(syllabus["topics"]) == 2
    assert not syllabus["active"]
    confirmed = service.confirm_syllabus(
        course["id"],
        [
            {"topic_id": t["id"], "source_ids": t["source_ids"]}
            for t in syllabus["topics"]
        ],
    )
    assert confirmed["active"]
    before = service.learning(course["id"])["syllabus_progress"]
    assert before["material_available"] >= 1 and before["studied"] == 0
    service.mark_studied(course["id"], confirmed["topics"][0]["id"], True)
    after = service.learning(course["id"])["syllabus_progress"]
    assert after["studied"] == 1
    assert (
        settings.pocketta_data_dir / "courses" / course["id"] / "syllabus.md"
    ).exists()
