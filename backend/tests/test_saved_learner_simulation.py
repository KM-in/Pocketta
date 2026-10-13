import pytest

from backend.app.tools.simulate_saved_learners import simulate


@pytest.mark.asyncio
async def test_saved_learner_simulation_uses_attempts_and_persists_evidence():
    result = await simulate()

    assert len(result["profiles"]) == 3
    assert result["question_bank_validation"]["question_count"] == 12
    assert result["question_bank_validation"]["keys_are_options"] == 12
    assert result["question_bank_validation"]["answers_supported_by_cited_excerpt"] == 12
    assert result["question_bank_validation"]["prompts_unique"]
    for profile in result["profiles"].values():
        for strategy in ("adaptive", "fixed_topic_medium"):
            outcome = profile[strategy]
            assert outcome["questions"] == 30
            assert outcome["persisted_observations"] == 30
            assert 0 <= outcome["accuracy"] <= 1
            assert 0 <= outcome["exact_question_repetition_rate"] < 1
    assert (
        result["mean_metrics"]["adaptive"]["exact_question_repetition_rate"]
        < result["mean_metrics"]["fixed_topic_medium"]["exact_question_repetition_rate"]
    )
