import csv

import pytest

from backend.app.tools.summarize_human_review import DIMENSIONS, summarize


def write_packet(path, *, second_rater="0.5", adjudicated=""):
    fields = ["item_id", "topic", "question", "options_json", "answer_key", "cited_evidence"]
    fields.extend(f"{rater}_{dimension}" for rater in ("rater_1", "rater_2") for dimension in DIMENSIONS)
    fields.extend(f"adjudicated_{dimension}" for dimension in DIMENSIONS)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for index in range(2):
            row = {
                "item_id": f"HQ-{index + 1}", "topic": "Processes", "question": "What is a process?",
                "options_json": '["running program", "program file"]', "answer_key": "running program",
                "cited_evidence": "A process is a program in execution.",
            }
            for dimension in DIMENSIONS:
                row[f"rater_1_{dimension}"] = "1"
                row[f"rater_2_{dimension}"] = second_rater
                row[f"adjudicated_{dimension}"] = adjudicated
            writer.writerow(row)


def test_summarizes_ratings_agreement_and_adjudication(tmp_path):
    packet = tmp_path / "review.csv"
    write_packet(packet, adjudicated="1")

    result = summarize(packet)

    assert result["sample_size"] == 2
    assert result["dimensions"]["correctness"]["rater_1_mean"] == 1
    assert result["dimensions"]["correctness"]["rater_2_mean"] == 0.5
    assert result["dimensions"]["correctness"]["exact_agreement_count"] == 0
    assert result["overall_exact_agreement_rate"] == 0
    assert result["items_with_any_reviewer_disagreement"] == 2
    assert result["adjudicated_items"] == 2
    assert result["adjudication_rate"] == 1


def test_rejects_incomplete_reviewer_packet(tmp_path):
    packet = tmp_path / "review.csv"
    write_packet(packet)
    with packet.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
        fields = rows[0].keys()
    rows[0]["rater_1_correctness"] = ""
    with packet.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="missing or invalid rater_1_correctness"):
        summarize(packet)


def test_rejects_scores_outside_the_declared_scale(tmp_path):
    packet = tmp_path / "review.csv"
    write_packet(packet, second_rater="0.75")

    with pytest.raises(ValueError, match="use 0, 0.5, or 1"):
        summarize(packet)


def test_rejects_partial_adjudication(tmp_path):
    packet = tmp_path / "review.csv"
    write_packet(packet, adjudicated="1")
    with packet.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    rows[0]["adjudicated_clarity"] = ""
    with packet.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(ValueError, match="incomplete adjudication scores"):
        summarize(packet)
