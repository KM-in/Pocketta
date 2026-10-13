"""Run a DeepEval RAG evaluation against PocketTA's synthetic OS fixture.

This invokes the configured tutor and uses the configured Cerebras model as the
DeepEval judge. Only synthetic fixture content is sent to the provider.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import tempfile
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

import httpx
from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
)
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

from ..config import Settings
from ..courses import CourseStore
from ..database import Database
from ..services.gateway import strict_schema
from ..services.knowledge import KnowledgeService
from ..services.providers import text_adapter
from ..services.tutor import TutorService, initialize_tutor
from .evaluate_retrieval import FIXTURE, seed_fixture


class CerebrasJudge(DeepEvalBaseLLM):
    """Minimal DeepEval model adapter using PocketTA's configured text provider."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.adapter = text_adapter(settings)
        super().__init__(model=f"{self.adapter.name}/{settings.text_model}")

    def load_model(self):
        return self

    def get_model_name(self):
        return f"{self.adapter.name}:{self.settings.text_model}"

    def _payload(self, prompt: str, schema=None):
        payload = {
            "model": self.settings.text_model,
            "messages": [{"role": "user", "content": str(prompt)}],
            "temperature": 0,
            "max_tokens": 2048,
        }
        if schema is not None:
            schema_json = (
                schema.model_json_schema()
                if hasattr(schema, "model_json_schema")
                else schema
            )
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": getattr(schema, "__name__", "deepeval_result").lower(),
                    "strict": True,
                    "schema": strict_schema(schema_json),
                },
            }
        return self.adapter.chat_payload(payload)

    def generate(self, prompt: str, schema=None) -> str:
        with httpx.Client(
            timeout=self.settings.generation_timeout_seconds, trust_env=False
        ) as client:
            response = client.post(
                f"{self.adapter.base_url}/chat/completions",
                headers=self.adapter.headers,
                json=self._payload(prompt, schema),
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]

    async def a_generate(self, prompt: str, schema=None) -> str:
        async with httpx.AsyncClient(
            timeout=self.settings.generation_timeout_seconds, trust_env=False
        ) as client:
            response = await client.post(
                f"{self.adapter.base_url}/chat/completions",
                headers=self.adapter.headers,
                json=self._payload(prompt, schema),
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]


async def evaluate(output_path: Path, *, max_cases: int = 6):
    fixture = json.loads(FIXTURE.read_text())
    questions = [q for q in fixture["questions"] if q["expected"]][:max_cases]
    if not questions:
        raise ValueError("The fixture contains no supported questions")

    with tempfile.TemporaryDirectory(prefix="pocketta-deepeval-") as directory:
        settings = Settings(pocketta_data_dir=Path(directory), knowledge_infer_topics=False)
        if settings.model_provider != "cerebras" or not settings.cerebras_api_key:
            raise RuntimeError("Configure MODEL_PROVIDER=cerebras and CEREBRAS_API_KEY")
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
        judge = CerebrasJudge(settings)
        metrics = [
            FaithfulnessMetric(model=judge, include_reason=True, async_mode=False),
            AnswerRelevancyMetric(model=judge, include_reason=True, async_mode=False),
            ContextualPrecisionMetric(model=judge, include_reason=True, async_mode=False),
            ContextualRecallMetric(model=judge, include_reason=True, async_mode=False),
        ]

        supported_results = []
        for question in questions:
            with db._connect() as connection:
                connection.execute(
                    "DELETE FROM tutor_turns WHERE course_id=?", (course["id"],)
                )
            bundle = await knowledge.retrieve(course["id"], question["query"], 3)
            tutor_bundle = await knowledge.retrieve(course["id"], question["query"], 6)
            turn = await tutor.ask(course["id"], question["query"], "explain")
            actual_output = " ".join(claim["text"] for claim in turn["claims"])
            answered = turn["status"] == "answered" and bool(actual_output.strip())
            if not answered:
                actual_output = "The uploaded course material does not provide enough evidence to answer this question."
            case = LLMTestCase(
                input=question["query"],
                actual_output=actual_output,
                expected_output=question["answer"],
                retrieval_context=[item.excerpt for item in bundle.items],
                context=[item.excerpt for item in bundle.items],
            )
            metric_results = {}
            for metric in metrics:
                # Answer-quality metrics apply only when the tutor answered.
                # Retrieval metrics still apply to all supported questions.
                if not answered and not isinstance(
                    metric, (ContextualPrecisionMetric, ContextualRecallMetric)
                ):
                    continue
                metric.measure(case)
                metric_results[metric.__class__.__name__] = {
                    "score": metric.score,
                    "reason": metric.reason,
                    "success": metric.success,
                }
            supported_results.append(
                {
                    "query": question["query"],
                    "tutor_status": turn["status"],
                    "answer_quality_scored": answered,
                    "tutor_answer": actual_output,
                    "retrieved_count": len(tutor_bundle.items),
                    "metric_context_count": len(bundle.items),
                    "retrieval_mode": bundle.retrieval_mode,
                    "metrics": metric_results,
                }
            )

        unsupported = []
        for question in (q for q in fixture["questions"] if not q["expected"]):
            with db._connect() as connection:
                connection.execute(
                    "DELETE FROM tutor_turns WHERE course_id=?", (course["id"],)
                )
            turn = await tutor.ask(course["id"], question["query"], "explain")
            unsupported.append(
                {"query": question["query"], "tutor_status": turn["status"]}
            )

        score_names = [metric.__class__.__name__ for metric in metrics]
        metric_case_counts = {
            name: sum(name in result["metrics"] for result in supported_results)
            for name in score_names
        }
        summary = {
            name: statistics.mean(
                result["metrics"][name]["score"]
                for result in supported_results
                if name in result["metrics"]
            )
            if metric_case_counts[name]
            else None
            for name in score_names
        }
        answered_count = sum(
            result["answer_quality_scored"] for result in supported_results
        )
        report = {
            "framework": "DeepEval",
            "framework_version": version("deepeval"),
            "created_at": datetime.now(UTC).isoformat(),
            "fixture": "synthetic-os-course-v1",
            "provider": settings.model_provider,
            "generation_model": settings.text_model,
            "judge_model": judge.get_model_name(),
            "case_method": "Tutor history cleared before every independent fixture question",
            "retrieval_mode": sorted(
                {result["retrieval_mode"] for result in supported_results}
            ),
            "supported_case_count": len(supported_results),
            "answered_supported_case_count": answered_count,
            "supported_answer_coverage": answered_count / len(supported_results),
            "supported_refusal_count": len(supported_results) - answered_count,
            "unsupported_case_count": len(unsupported),
            "mean_metrics": summary,
            "metric_case_counts": metric_case_counts,
            "unsupported_refusal_accuracy": sum(
                result["tutor_status"] == "unsupported" for result in unsupported
            )
            / len(unsupported)
            if unsupported
            else None,
            "supported_cases": supported_results,
            "unsupported_cases": unsupported,
            "limitations": [
                "The held-out fixture contains synthetic short excerpts and only six supported questions.",
                "Judge metrics are model-based estimates and were scored with the configured provider/model shown above.",
                "Faithfulness and answer relevancy are averaged over answered supported cases; answer coverage is reported separately. Context precision and recall cover all supported fixture cases.",
                "This run does not evaluate question quality or real learner outcomes.",
                "Semantic embeddings are omitted when no embedding service is configured; retrieval mode is recorded per case.",
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
        default=Path("docs/evaluation/track-d-deepeval-2026-10-13.json"),
    )
    parser.add_argument("--max-cases", type=int, default=6)
    args = parser.parse_args()
    result = asyncio.run(evaluate(args.output, max_cases=args.max_cases))
    print(json.dumps({k: v for k, v in result.items() if k not in {"supported_cases", "unsupported_cases"}}, indent=2))
