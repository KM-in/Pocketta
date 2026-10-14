"""Reproducible synthetic held-out retrieval smoke evaluation (not a learning benchmark)."""

import argparse
import asyncio
import json
import os
import tempfile
import uuid
from pathlib import Path

from ..config import Settings
from ..courses import CourseStore
from ..database import Database
from ..services.knowledge import KnowledgeService

FIXTURE = (
    Path(__file__).resolve().parents[2] / "tests/fixtures/knowledge/os-course.json"
)


def seed_fixture(store, fixture):
    course = store.create_course(fixture["title"], fixture["description"])
    locations = {}
    for source in fixture["sources"]:
        source_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"{course['id']}:{source['key']}")
        )
        with store.db._connect() as c:
            c.execute(
                "INSERT INTO sources(id,course_id,name,type,file_path,status,created_at) VALUES (?,?,?,?,?,'ready','fixture')",
                (source_id, course["id"], source["name"], source["type"], ""),
            )
        for unit in source["units"]:
            unit_id = store.save_unit(
                source_id, unit["location"], unit["text"], unit["text"]
            )
            with store.db._connect() as c:
                c.execute(
                    "UPDATE content_units SET uncertain=? WHERE id=?",
                    (unit.get("uncertain", False), unit_id),
                )
            locations[(source["key"], unit["location"])] = unit_id
    return course, locations


async def evaluate(live=False):
    fixture = json.loads(FIXTURE.read_text())
    with tempfile.TemporaryDirectory(prefix="pocketta-retrieval-") as directory:
        config = Settings(
            pocketta_data_dir=Path(directory),
            fastembed_cache_dir=(
                Path(
                    os.environ.get(
                        "FASTEMBED_CACHE_DIR",
                        Path.home() / ".cache" / "pocketta" / "fastembed",
                    )
                )
                if os.environ.get("EMBEDDING_PROVIDER", "fastembed") == "fastembed"
                else None
            ),
            knowledge_infer_topics=False,
            **(
                {}
                if live
                else {
                    "_env_file": None,
                    "openai_api_key": "",
                    "embedding_api_key": "",
                    "embedding_provider": "api",
                    "model_provider": "lm_studio",
                    "lm_studio_model_id": "",
                }
            ),
        )
        if live and not config.embedding_enabled:
            raise RuntimeError(
            "Live embeddings were requested, but no embedding API key or local embedding endpoint is configured"
            )
        db = Database(config.database_path)
        db.initialize()
        store = CourseStore(db)
        store.initialize()
        course, locations = seed_fixture(store, fixture)
        service = KnowledgeService(config, store)
        for source in store.sources(course["id"]):
            await service.index_source(source["id"], build_summaries=False)
        results = []
        for question in fixture["questions"]:
            bundle = await service.retrieve(course["id"], question["query"], 3)
            expected = {
                locations[(e["source"], e["location"])] for e in question["expected"]
            }
            actual = {item.content_unit_id for item in bundle.items}
            hits = len(expected & actual)
            results.append(
                {
                    "query": question["query"],
                    "expected_count": len(expected),
                    "returned_count": len(actual),
                    "precision": hits / len(actual) if actual else None,
                    "recall": hits / len(expected) if expected else None,
                    "source_location_hit": bool(hits) if expected else None,
                    "unsupported_correct": not actual if not expected else None,
                    "mode": bundle.retrieval_mode,
                    "semantic_passage_matches": bundle.diagnostics[
                        "passage_semantic_matches"
                    ],
                    "keyword_passage_matches": bundle.diagnostics[
                        "passage_keyword_matches"
                    ],
                }
            )
        supported = [r for r in results if r["expected_count"]]
        unsupported = [r for r in results if not r["expected_count"]]
        return {
            "fixture": "synthetic-os-course-v1",
            "live_embeddings_requested": live,
            "source_location_hit_rate": sum(r["source_location_hit"] for r in supported)
            / len(supported),
            "unsupported_accuracy": sum(r["unsupported_correct"] for r in unsupported)
            / len(unsupported),
            "queries_with_semantic_passage_matches": sum(
                r["semantic_passage_matches"] > 0 for r in results
            ),
            "results": results,
            "limitations": "Synthetic excerpts and location fixtures; does not measure tutor faithfulness, question quality, or learning outcomes. Offline mode tests keyword retrieval only.",
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-embeddings",
        action="store_true",
        help="Embed synthetic fixture text and queries using the configured embedding provider",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the JSON report to this path instead of stdout",
    )
    args = parser.parse_args()
    output = json.dumps(asyncio.run(evaluate(args.live_embeddings)), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output)
    else:
        print(output, end="")
