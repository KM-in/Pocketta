"""Measure repeat-run tutor answer coverage on the synthetic OS fixture."""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from ..config import Settings
from ..courses import CourseStore
from ..database import Database
from ..services.knowledge import KnowledgeService
from ..services.tutor import TutorService, initialize_tutor
from .evaluate_retrieval import FIXTURE, seed_fixture


def summarize_runs(runs: list[dict]) -> dict:
    supported = [case for run in runs for case in run["supported_cases"]]
    answers_by_query: dict[str, int] = {}
    attempts_by_query: dict[str, int] = {}
    for case in supported:
        query = case["query"]
        attempts_by_query[query] = attempts_by_query.get(query, 0) + 1
        answers_by_query[query] = answers_by_query.get(query, 0) + int(
            case["status"] == "answered"
        )
    per_query = [
        {
            "query": query,
            "attempts": attempts_by_query[query],
            "answered": answers_by_query[query],
            "coverage": answers_by_query[query] / attempts_by_query[query],
        }
        for query in attempts_by_query
    ]
    total = len(supported)
    answer_count = sum(case["status"] == "answered" for case in supported)
    return {
        "repeat_count": len(runs),
        "supported_question_count": len(per_query),
        "supported_attempt_count": total,
        "answered_attempt_count": answer_count,
        "overall_answer_coverage": answer_count / total if total else None,
        "mean_per_question_coverage": statistics.mean(
            item["coverage"] for item in per_query
        )
        if per_query
        else None,
        "always_answered_question_count": sum(
            item["answered"] == item["attempts"] for item in per_query
        ),
        "per_question": per_query,
    }


async def evaluate(output_path: Path, *, repeats: int = 3):
    if not 2 <= repeats <= 5:
        raise ValueError("Use 2-5 repeats")
    fixture = json.loads(FIXTURE.read_text())
    questions = [item for item in fixture["questions"] if item["expected"]]
    settings = Settings(knowledge_infer_topics=False)
    if settings.model_provider != "cerebras" or not settings.cerebras_api_key:
        raise RuntimeError("Configure MODEL_PROVIDER=cerebras and CEREBRAS_API_KEY")

    with tempfile.TemporaryDirectory(prefix="pocketta-tutor-coverage-") as directory:
        settings = Settings(
            pocketta_data_dir=Path(directory), knowledge_infer_topics=False
        )
        db = Database(settings.database_path)
        db.initialize()
        store = CourseStore(db)
        store.initialize()
        initialize_tutor(db)
        course, _ = seed_fixture(store, fixture)
        knowledge = KnowledgeService(settings, store)
        for source in store.sources(course["id"]):
            await knowledge.index_source(source["id"], build_summaries=False)
        tutor = TutorService(settings, store, knowledge)

        runs = []
        for repeat in range(1, repeats + 1):
            cases = []
            for question in questions:
                with db._connect() as connection:
                    connection.execute(
                        "DELETE FROM tutor_turns WHERE course_id=?", (course["id"],)
                    )
                retrieved = await knowledge.retrieve(
                    course["id"], question["query"], 6
                )
                turn = await tutor.ask(course["id"], question["query"], "explain")
                cases.append(
                    {
                        "query": question["query"],
                        "status": turn["status"],
                        "retrieved_evidence_count": len(retrieved.items),
                        "used_citation_count": len(turn["evidence"]["items"]),
                        "claims": turn["claims"],
                    }
                )
            runs.append({"repeat": repeat, "supported_cases": cases})

        report = {
            "created_at": datetime.now(UTC).isoformat(),
            "fixture": "synthetic-os-course-v1",
            "provider": settings.model_provider,
            "generation_model": settings.text_model,
            "method": "Actual TutorService with tutor history cleared before each independent fixture question; each repeat uses the same question order",
            "summary": summarize_runs(runs),
            "runs": runs,
            "limitations": [
                "Only six supported questions from a small synthetic fixture are used.",
                "The result measures response coverage and repeat stability, not answer faithfulness or learning outcomes.",
                "Provider sampling may vary; three repeats are not a reliability guarantee.",
                "Unsupported-question refusal is measured separately in the DeepEval report.",
            ],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n")
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/evaluation/tutor-coverage-2026-10-14.json"),
    )
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.output, repeats=args.repeats))
    print(json.dumps(result["summary"], indent=2))
