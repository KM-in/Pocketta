"""Deterministic-seed toy comparison of adaptive and fixed topic selection."""

import json
import random
import statistics

from ..services.quizzes import bkt_mastery_probability


PROFILES = {
    "new_learner": {"processes": 0.24, "threads": 0.24, "scheduling": 0.24, "deadlocks": 0.24},
    "uneven_learner": {"processes": 0.78, "threads": 0.27, "scheduling": 0.43, "deadlocks": 0.22},
    "returning_learner": {"processes": 0.72, "threads": 0.64, "scheduling": 0.77, "deadlocks": 0.58},
}
SESSIONS = 6
QUESTIONS_PER_SESSION = 5
DIFFICULTY_COST = {"easy": -0.15, "medium": 0.0, "challenging": 0.18}


def _clamp(value):
    return max(0.05, min(0.95, value))


def _run(initial, adaptive, seed):
    rng = random.Random(seed)
    ability = dict(initial)
    evidence = {topic: [] for topic in initial}
    seen_items = set()
    repeated_items = 0
    total = correct = 0
    cursor = 0
    for session in range(SESSIONS):
        for question in range(QUESTIONS_PER_SESSION):
            topics = list(initial)
            if adaptive:
                topic = min(
                    topics,
                    key=lambda name: (
                        bkt_mastery_probability(evidence[name]),
                        (topics.index(name) - cursor) % len(topics),
                    ),
                )
                cursor = (topics.index(topic) + 1) % len(topics)
                estimate = bkt_mastery_probability(evidence[topic])
                difficulty = "easy" if estimate < 0.45 else "medium" if estimate < 0.8 else "challenging"
            else:
                topic = topics[(session * QUESTIONS_PER_SESSION + question) % len(topics)]
                difficulty = "medium"
            item = (topic, difficulty)
            repeated_items += item in seen_items
            seen_items.add(item)
            probability = _clamp(ability[topic] - DIFFICULTY_COST[difficulty])
            was_correct = rng.random() < probability
            correct += was_correct
            total += 1
            evidence[topic].append({"score": float(was_correct)})
            # Explicit simulated learning assumption: every practice item helps,
            # with a larger expected gain after a correct response.
            ability[topic] = _clamp(ability[topic] + (0.035 if was_correct else 0.02))
    return {
        "accuracy": correct / total,
        "mean_skill_gain": statistics.mean(ability.values()) - statistics.mean(initial.values()),
        "topic_difficulty_pair_repetition_rate": repeated_items / total,
        "questions": total,
    }


def simulate():
    per_profile = {}
    for index, (name, initial) in enumerate(PROFILES.items()):
        per_profile[name] = {
            "adaptive": _run(initial, True, 20261013 + index),
            "fixed_topic_medium": _run(initial, False, 20261013 + index),
        }
    metrics = {}
    for strategy in ("adaptive", "fixed_topic_medium"):
        metrics[strategy] = {
            key: statistics.mean(result[strategy][key] for result in per_profile.values())
            for key in ("accuracy", "mean_skill_gain", "topic_difficulty_pair_repetition_rate")
        }
    return {
        "profiles": per_profile,
        "mean_metrics": metrics,
        "assumptions": {
            "sessions": SESSIONS,
            "questions_per_session": QUESTIONS_PER_SESSION,
            "topics": list(next(iter(PROFILES.values()))),
            "adaptive_policy": "Select the lowest BKT posterior topic; easy below 0.45, medium below 0.80, challenging otherwise.",
            "fixed_baseline": "Rotate topics in fixed order and use medium difficulty.",
            "simulated_learning": "Underlying skill rises by 0.035 after a correct answer and 0.020 after an incorrect answer; probability of a correct response is skill minus a difficulty offset.",
            "seed": 20261013,
            "limitation": "Toy simulation only. It does not validate real learner gains, question quality, or the BKT parameter calibration.",
        },
    }


if __name__ == "__main__":
    print(json.dumps(simulate(), indent=2))
