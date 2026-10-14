"""Validate and summarize the independent human question-review CSV."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

DIMENSIONS = (
    "correctness",
    "clarity",
    "single_best_answer",
    "evidence_support",
)
RATERS = ("rater_1", "rater_2")
ALLOWED_SCORES = {"0", "0.5", "1"}


def summarize(path: Path) -> dict:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        fields = set(reader.fieldnames or [])

    score_fields = [f"{rater}_{dimension}" for rater in RATERS for dimension in DIMENSIONS]
    adjudicated_fields = [f"adjudicated_{dimension}" for dimension in DIMENSIONS]
    required = {
        "item_id", "topic", "question", "options_json", "answer_key", "cited_evidence",
        *score_fields, *adjudicated_fields,
    }
    missing_fields = sorted(required - fields)
    if missing_fields:
        raise ValueError(f"Review CSV is missing required columns: {', '.join(missing_fields)}")
    if not rows:
        raise ValueError("Review CSV contains no questions")

    item_ids = [row["item_id"].strip() for row in rows]
    if any(not item_id for item_id in item_ids) or len(set(item_ids)) != len(item_ids):
        raise ValueError("Every row must have a non-empty, unique item_id")

    for row in rows:
        for field in score_fields:
            value = row[field].strip()
            if value not in ALLOWED_SCORES:
                raise ValueError(
                    f"{row['item_id']} has a missing or invalid {field}; use 0, 0.5, or 1"
                )
        adjudicated = [row[field].strip() for field in adjudicated_fields]
        if any(adjudicated) and not all(value in ALLOWED_SCORES for value in adjudicated):
            raise ValueError(
                f"{row['item_id']} has incomplete adjudication scores; fill all four or leave all blank"
            )

    dimensions = {}
    agreement_cells = agreement_count = 0
    disagreement_items = set()
    adjudicated_items = 0
    for dimension in DIMENSIONS:
        rater_values = {
            rater: [float(row[f"{rater}_{dimension}"]) for row in rows]
            for rater in RATERS
        }
        dimension_agreements = sum(
            row[f"{RATERS[0]}_{dimension}"].strip()
            == row[f"{RATERS[1]}_{dimension}"].strip()
            for row in rows
        )
        agreement_cells += len(rows)
        agreement_count += dimension_agreements
        dimensions[dimension] = {
            **{
                f"{rater}_mean": round(statistics.mean(values), 4)
                for rater, values in rater_values.items()
            },
            **{
                f"{rater}_zero_count": sum(value == 0 for value in values)
                for rater, values in rater_values.items()
            },
            "exact_agreement_count": dimension_agreements,
            "exact_agreement_rate": round(dimension_agreements / len(rows), 4),
        }
        adjudicated_values = [
            float(row[f"adjudicated_{dimension}"])
            for row in rows
            if row[f"adjudicated_{dimension}"].strip() in ALLOWED_SCORES
        ]
        dimensions[dimension]["adjudicated_mean"] = (
            round(statistics.mean(adjudicated_values), 4) if adjudicated_values else None
        )
        dimensions[dimension]["adjudicated_zero_count"] = sum(
            value == 0 for value in adjudicated_values
        )

    for row in rows:
        if any(
            row[f"{RATERS[0]}_{name}"].strip()
            != row[f"{RATERS[1]}_{name}"].strip()
            for name in DIMENSIONS
        ):
            disagreement_items.add(row["item_id"].strip())
        if all(row[field].strip() in ALLOWED_SCORES for field in adjudicated_fields):
            adjudicated_items += 1

    return {
        "sample_size": len(rows),
        "rating_scale": [0, 0.5, 1],
        "dimensions": dimensions,
        "overall_exact_agreement_rate": round(agreement_count / agreement_cells, 4),
        "items_with_any_reviewer_disagreement": len(disagreement_items),
        "adjudicated_items": adjudicated_items,
        "adjudication_rate": round(adjudicated_items / len(rows), 4),
        "interpretation_note": "Descriptive agreement and ratings for this sample only; these are not evidence of learning gains or broad subject coverage.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="Completed human-review CSV")
    parser.add_argument("--output", type=Path, help="Optional JSON output path")
    args = parser.parse_args()
    result = summarize(args.csv_path)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
