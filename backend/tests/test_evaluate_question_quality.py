import pytest

pytest.importorskip("deepeval")

from backend.app.tools.evaluate_question_quality import prompt_repetition


def test_prompt_repetition_counts_exact_and_near_duplicate_pairs():
    result = prompt_repetition(
        [
            "What defines a process address space?",
            "What defines a process address space!",
            "Process address space defines the process",
            "How does deadlock affect scheduling?",
        ],
        threshold=0.5,
    )

    assert result["compared_pair_count"] == 6
    assert result["exact_repeat_pair_count"] == 1
    assert result["near_duplicate_pair_count"] == 2
    assert result["repetition_rate"] == 0.5
