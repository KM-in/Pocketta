"""Simulate learners through saved PocketTA quiz attempts and BKT updates.

Questions are hand-authored against a synthetic course fixture and stored as
ready quizzes before attempts begin. The simulation uses the production
create_attempt/save_answers/submit path, but does not call a generation model.
"""

from __future__ import annotations

import asyncio
import argparse
import json
import random
import statistics
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ..config import Settings
from ..courses import CourseStore
from ..database import Database
from ..services.knowledge import KnowledgeService
from ..services.quizzes import QuizService, initialize_quizzes, topic_id
from .evaluate_retrieval import seed_fixture


PROFILES = {
    "new_learner": {"Processes": 0.24, "Threads": 0.24, "Deadlocks": 0.24, "Scheduling": 0.24},
    "uneven_learner": {"Processes": 0.78, "Threads": 0.27, "Deadlocks": 0.22, "Scheduling": 0.43},
    "returning_learner": {"Processes": 0.72, "Threads": 0.64, "Deadlocks": 0.58, "Scheduling": 0.77},
}
SESSIONS = 6
QUESTIONS_PER_SESSION = 5
DIFFICULTY_COST = {"easy": -0.15, "medium": 0.0, "challenging": 0.18}
QUESTION_BANK = {
    ("Processes", "easy"): {
        "prompt": "Which record stores a process's state during a context switch?",
        "answer": "Process control block",
    },
    ("Processes", "medium"): {
        "prompt": "How does the source distinguish a process from a program file?",
        "answer": "A process is a program in execution with its own address space",
    },
    ("Processes", "challenging"): {
        "prompt": "What address-space arrangement does the source assign to separate processes?",
        "answer": "Each process has its own address space",
    },
    ("Threads", "easy"): {
        "prompt": "Name one resource that threads in the same process share.",
        "answer": "Code, data, or open files are shared",
    },
    ("Threads", "medium"): {
        "prompt": "Which execution state remains specific to an individual thread?",
        "answer": "Its stack and registers",
    },
    ("Threads", "challenging"): {
        "prompt": "What lets threads execute concurrently while remaining in one process?",
        "answer": "They share one process address space while each keeps its own stack and registers",
    },
    ("Deadlocks", "easy"): {
        "prompt": "Which condition says a resource cannot be used by multiple processes at once?",
        "answer": "Mutual exclusion",
    },
    ("Deadlocks", "medium"): {
        "prompt": "List the four necessary conditions for deadlock.",
        "answer": "Mutual exclusion, hold and wait, no preemption, and circular wait",
    },
    ("Deadlocks", "challenging"): {
        "prompt": "How does the source define a deadlock among processes?",
        "answer": "Processes wait forever for resources held by other members of the set",
    },
    ("Scheduling", "easy"): {
        "prompt": "What fixed allowance does round robin give each ready process?",
        "answer": "A fixed time quantum",
    },
    ("Scheduling", "medium"): {
        "prompt": "Where does a round-robin process go when its time quantum expires?",
        "answer": "To the back of the ready queue",
    },
    ("Scheduling", "challenging"): {
        "prompt": "What causes the convoy effect under first-come first-served scheduling?",
        "answer": "A long CPU burst delays shorter jobs",
    },
}
SUPPORT_PHRASES = {
    ("Processes", "easy"): "process control block",
    ("Processes", "medium"): "program in execution",
    ("Processes", "challenging"): "address space",
    ("Threads", "easy"): "code, data, and open files",
    ("Threads", "medium"): "stack and registers",
    ("Threads", "challenging"): "concurrent execution",
    ("Deadlocks", "easy"): "mutual exclusion",
    ("Deadlocks", "medium"): "necessary deadlock conditions",
    ("Deadlocks", "challenging"): "waits forever",
    ("Scheduling", "easy"): "time quantum",
    ("Scheduling", "medium"): "ready queue",
    ("Scheduling", "challenging"): "convoy effect",
}
OPTIONS = {
    "Processes": ["Process control block", "Ready queue", "Page table", "File descriptor"],
    "Threads": ["Its stack and registers", "The process code only", "The process data only", "All other threads' registers"],
    "Deadlocks": ["Mutual exclusion", "Round robin", "Time quantum", "Page replacement"],
    "Scheduling": ["To the back of the ready queue", "To the front of the ready queue", "Out of the process address space", "Into the process control block"],
}


def _clamp(value):
    return max(0.05, min(0.95, value))


async def _seed_bank(store, course, knowledge, service):
    evidence_by_question = {}
    for (topic, difficulty), spec in QUESTION_BANK.items():
        bundle = await knowledge.retrieve(course["id"], spec["prompt"], 6)
        phrase = SUPPORT_PHRASES[(topic, difficulty)]
        item = next(
            (entry for entry in bundle.items if phrase in entry.excerpt.casefold()),
            None,
        )
        if item is None:
            raise RuntimeError(f"No fixture evidence supports {topic} / {difficulty}")
        evidence_by_question[(topic, difficulty)] = item

    now = datetime.now(UTC).isoformat()
    bank_checks = []
    for (topic, difficulty), spec in QUESTION_BANK.items():
        item = evidence_by_question[(topic, difficulty)]
        question_id = f"fixture-{topic.casefold()}-{difficulty}"
        options = OPTIONS[topic]
        answer = spec["answer"]
        if answer not in options:
            options = [answer, *[option for option in options if option != answer][:3]]
        question = {
            "id": question_id,
            "kind": "mcq",
            "topic": topic,
            "topic_id": topic_id(topic),
            "difficulty": difficulty,
            "prompt": spec["prompt"],
            "options": options,
            "answer": answer,
            "rubric": "Select the option supported by the cited synthetic course excerpt.",
            "explanation": answer,
            "chunk_ids": [item.chunk_id],
            "source_ids": [item.source_id],
            "version": 1,
            "numeric_answer": None,
            "tolerance": None,
            "unit": "",
        }
        bank_checks.append(
            {
                "question_id": question_id,
                "answer_is_an_option": answer in options,
                "citation_contains_expected_fact": SUPPORT_PHRASES[(topic, difficulty)]
                in item.excerpt.casefold(),
                "topic": topic,
                "difficulty": difficulty,
            }
        )
        source_snapshots = service._snapshot(course["id"], [item.source_id])
        quiz_id = str(uuid.uuid5(uuid.NAMESPACE_URL, question_id))
        with store.db._connect() as connection:
            connection.execute(
                """INSERT INTO course_quizzes(id,course_id,pack_id,title,status,instructions_json,
                snapshots_json,profile_json,questions_json,warnings_json,stale,created_at,updated_at)
                VALUES(?,?,NULL,?,'ready',?,?,?,?, '[]',0,?,?)""",
                (
                    quiz_id,
                    course["id"],
                    f"Synthetic fixture · {topic} · {difficulty}",
                    json.dumps({"fixture": "hand-authored synthetic MCQ"}),
                    json.dumps(source_snapshots),
                    json.dumps(service._profile(course["id"])),
                    json.dumps([question]),
                    now,
                    now,
                ),
            )
        question["quiz_id"] = quiz_id
    prompts = [spec["prompt"].casefold().strip() for spec in QUESTION_BANK.values()]
    return {
        "question_count": len(bank_checks),
        "question_ids_unique": len({row["question_id"] for row in bank_checks})
        == len(bank_checks),
        "prompts_unique": len(set(prompts)) == len(prompts),
        "keys_are_options": sum(row["answer_is_an_option"] for row in bank_checks),
        "answers_supported_by_cited_excerpt": sum(
            row["citation_contains_expected_fact"] for row in bank_checks
        ),
        "checks": bank_checks,
        "limitation": "These deterministic checks apply only to the hand-authored simulator fixture, not to model-generated question quality or ambiguity.",
    }


async def _run_profile(initial, adaptive, seed):
    rng = random.Random(seed)
    ability = dict(initial)
    with tempfile.TemporaryDirectory(prefix="pocketta-saved-learners-") as directory:
        settings = Settings(
            _env_file=None,
            pocketta_data_dir=Path(directory),
            openai_api_key="",
            embedding_api_key="",
            model_provider="lm_studio",
            lm_studio_model_id="",
            knowledge_infer_topics=False,
        )
        db = Database(settings.database_path)
        db.initialize()
        store = CourseStore(db)
        store.initialize()
        initialize_quizzes(db)
        from .evaluate_retrieval import FIXTURE

        fixture = json.loads(FIXTURE.read_text())
        course, _ = seed_fixture(store, fixture)
        knowledge = KnowledgeService(settings, store)
        for source in store.sources(course["id"]):
            await knowledge.index_source(source["id"], build_summaries=False)
        service = QuizService(settings, store, knowledge)
        bank_validation = await _seed_bank(store, course, knowledge, service)

        question_runs = []
        pair_runs = []
        total = correct = 0
        cursor = 0
        for session in range(SESSIONS):
            for _ in range(QUESTIONS_PER_SESSION):
                topics = list(initial)
                profile = {item["title"]: item for item in service._profile(course["id"])}
                estimates = {
                    topic: profile.get(topic, {}).get("mastery_probability") or 0.20
                    for topic in topics
                }
                if adaptive:
                    topic = min(
                        topics,
                        key=lambda name: (
                            estimates[name], (topics.index(name) - cursor) % len(topics)
                        ),
                    )
                    cursor = (topics.index(topic) + 1) % len(topics)
                    estimate = estimates[topic]
                    difficulty = "easy" if estimate < 0.45 else "medium" if estimate < 0.8 else "challenging"
                else:
                    topic = topics[len(question_runs) % len(topics)]
                    difficulty = "medium"

                question_id = f"fixture-{topic.casefold()}-{difficulty}"
                quiz_id = str(uuid.uuid5(uuid.NAMESPACE_URL, question_id))
                with store.db._connect() as connection:
                    saved = json.loads(
                        connection.execute(
                            "SELECT questions_json FROM course_quizzes WHERE id=?", (quiz_id,)
                        ).fetchone()[0]
                    )[0]
                probability = _clamp(ability[topic] - DIFFICULTY_COST[difficulty])
                was_correct = rng.random() < probability
                response = saved["answer"] if was_correct else next(
                    option for option in saved["options"] if option != saved["answer"]
                )

                attempt = service.create_attempt(course["id"], quiz_id)
                service.save_answers(course["id"], attempt["id"], {question_id: response})
                completed = await service.submit(course["id"], attempt["id"])
                if completed["status"] != "completed":
                    raise RuntimeError("Simulation attempt did not complete")
                grade = completed["grades"][question_id]
                actual_correct = float(grade["score"]) == 1.0
                correct += actual_correct
                total += 1
                question_runs.append(question_id)
                pair_runs.append((topic, difficulty))
                ability[topic] = _clamp(ability[topic] + (0.035 if was_correct else 0.02))

        observations = service.learning(course["id"])["topics"]
        count = sum(topic["observation_count"] for topic in observations)
        if count != total:
            raise RuntimeError(f"Expected {total} persisted observations, found {count}")
        return {
            "accuracy": correct / total,
            "mean_skill_gain": statistics.mean(ability.values()) - statistics.mean(initial.values()),
            "exact_question_repetition_rate": sum(
                question_runs[index] in question_runs[:index]
                for index in range(len(question_runs))
            ) / total,
            "topic_difficulty_pair_repetition_rate": sum(
                pair_runs[index] in pair_runs[:index]
                for index in range(len(pair_runs))
            ) / total,
            "questions": total,
            "persisted_observations": count,
            "unique_saved_question_ids": len(set(question_runs)),
            "final_topic_mastery": {
                topic["title"]: topic["mastery_probability"] for topic in observations
            },
            "question_bank_validation": bank_validation,
        }


async def simulate():
    profiles = {}
    for index, (name, initial) in enumerate(PROFILES.items()):
        profiles[name] = {
            "adaptive": await _run_profile(initial, True, 20261013 + index),
            "fixed_topic_medium": await _run_profile(initial, False, 20261013 + index),
        }
    means = {}
    for strategy in ("adaptive", "fixed_topic_medium"):
        means[strategy] = {
            metric: statistics.mean(
                result[strategy][metric]
                for result in profiles.values()
            )
            for metric in (
                "accuracy",
                "mean_skill_gain",
                "exact_question_repetition_rate",
                "topic_difficulty_pair_repetition_rate",
            )
        }
    bank_validation = profiles["new_learner"]["adaptive"]["question_bank_validation"]
    return {
        "profiles": profiles,
        "mean_metrics": means,
        "method": {
            "sessions_per_profile": SESSIONS,
            "questions_per_session": QUESTIONS_PER_SESSION,
            "saved_questions": len(QUESTION_BANK),
            "attempt_path": "QuizService.create_attempt -> save_answers -> submit; grades and topic observations are read back from SQLite.",
            "adaptive_policy": "Choose the lowest persisted BKT estimate; easy below 0.45, medium below 0.80, challenging otherwise.",
            "fixed_baseline": "Rotate topics in fixed order and use medium difficulty.",
            "seed": 20261013,
            "limitation": "Hand-authored questions and synthetic learner response/learning assumptions. This validates persistence/adaptation mechanics, not model question quality or real educational gains. Exact repetition counts compare saved question IDs across attempts.",
        },
        "question_bank_validation": bank_validation,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(simulate())
    serialized = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized)
    else:
        print(serialized, end="")
