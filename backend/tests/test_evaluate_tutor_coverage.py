from backend.app.tools.evaluate_tutor_coverage import summarize_runs


def test_summarize_runs_reports_overall_and_per_question_coverage():
    runs = [
        {
            "supported_cases": [
                {"query": "q1", "status": "answered"},
                {"query": "q2", "status": "unsupported"},
            ]
        },
        {
            "supported_cases": [
                {"query": "q1", "status": "answered"},
                {"query": "q2", "status": "answered"},
            ]
        },
    ]

    result = summarize_runs(runs)

    assert result["overall_answer_coverage"] == 0.75
    assert result["mean_per_question_coverage"] == 0.75
    assert result["always_answered_question_count"] == 1
    assert result["per_question"] == [
        {"query": "q1", "attempts": 2, "answered": 2, "coverage": 1.0},
        {"query": "q2", "attempts": 2, "answered": 1, "coverage": 0.5},
    ]
