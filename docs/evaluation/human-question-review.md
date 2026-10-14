# Independent question review packet

`human-question-review.csv` contains 14 unique questions sampled from the two saved production-path quality runs. Exact duplicate prompts across runs were deduplicated, and the remaining rows were shuffled and given blind IDs. The packet includes the answer key and only the cited synthetic source evidence; it deliberately omits the model judge's scores and explanations.

## Review protocol

Have two independent reviewers with operating-systems subject knowledge rate every row before they discuss disagreements. Use `1` for fully satisfactory, `0.5` for partially satisfactory or needing qualification, and `0` for a material failure. Enter the ratings in each reviewer's columns and use the notes fields to explain ambiguity or evidence gaps.

- **Correctness:** Is the keyed answer factually correct for the question?
- **Clarity:** Is the question self-contained and understandable without guessing its intent?
- **Single best answer:** Is exactly one listed option defensible? Rate `0` if another option is also reasonably correct.
- **Evidence support:** Does the supplied excerpt directly support the keyed answer and topic?

Reviewers should judge the item against the cited text and their subject knowledge, not infer what the model intended. Resolve disagreements only after both individual ratings are complete; enter agreed or adjudicated values and a short rationale in the adjudication columns. Keep the individual ratings unchanged. Report item count, means by dimension, zero ratings by dimension, exact reviewer agreement, and the adjudication rate alongside any model-judge metrics.

After both independent ratings are complete, validate and summarize the packet with:

```sh
.venv/bin/python -m backend.app.tools.summarize_human_review \
  docs/evaluation/human-question-review.csv \
  --output docs/evaluation/human-question-review-results.json
```

The command rejects missing ratings and values outside the declared scale. It reports each rater's mean and zero count by dimension, exact agreement, reviewer disagreements, and any adjudicated results. It cannot establish correctness on its own; the reviewers supply the evidence.

This is a ready-to-fill pilot packet, not an evaluation result. It contains 14 unique items from a small synthetic operating-systems fixture and cannot establish quality across subjects or learning gains. A larger sample and a held-out learner evaluation remain necessary.
