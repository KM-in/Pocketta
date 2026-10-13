# Generated question quality evaluation

## Method

`backend/app/tools/evaluate_question_quality.py` creates a temporary course from the synthetic OS fixture and generates two four-question MCQ sets through the production `QuizService.generate` path. This exercises the normal generation, source-citation checks, question verification, and saved-question duplicate rejection. Accepted question prompts, options, answers, and cited excerpts are then scored by a structured Cerebras judge.

The same Cerebras model family both generates and judges questions. Scores are model-based estimates, not independent or human labels. Each dimension is scored from 0 to 1: answer correctness, clarity, single-best-answer quality, and support from the cited source. Repetition compares every pair of accepted prompts using token-set Jaccard similarity; exact text matches count separately, and near duplicates use a threshold of 0.88.

## Results

| Run | Saved questions | Correctness | Clarity | Single best answer | Evidence support | Repeated pairs |
|---|---:|---:|---:|---:|---:|---:|
| Baseline verifier | 8 | 0.981 | 0.988 | 0.963 | 0.969 | 0/28 |
| Stricter verifier follow-up | 8 | 1.000 | 0.988 | 1.000 | 1.000 | 0/28 |

The baseline judge flagged one item for a potentially defensible second MCQ option (process control block). The production verifier was tightened to require exactly one defensible answer and reject distractors that could reasonably also be correct. In the follow-up sample, all eight accepted items received full correctness, single-answer, and evidence-support scores; the clarity mean was 0.988. Both runs had zero exact or near-duplicate pairs among accepted questions. The baseline run rejected two duplicate batches; the follow-up rejected none. These are two small model-judged samples, so their score difference does not establish that the verifier change improved quality.

The evaluator scores saved/accepted items only. `QuizService` does not expose the text of discarded candidates, so rejected duplicate batches are counted but not scored. The result files preserve per-question scores, reasons, options, answers, and synthetic evidence:

- [Baseline result](question-quality-baseline-2026-10-14.json)
- [Stricter-verifier follow-up](question-quality-remediated-2026-10-14.json)

## Reproduce

Install the optional evaluation dependency and configure Cerebras as described in [the DeepEval runbook](track-d-deepeval.md). Then run from the repository root:

```sh
python -m backend.app.tools.evaluate_question_quality \
  --output docs/evaluation/question-quality-run.json \
  --quiz-count 2 \
  --questions-per-quiz 4
```

The run makes real generation, verification, and judge requests and may incur provider usage. It sends only the synthetic OS fixture; no uploaded course material is used.

## Limits

The fixture contains only three OS topics and eight questions per run. It does not replace human review, a larger labeled ambiguity set, external subject-matter verification, or real-learner outcomes. The built-in verifier itself uses the same configured model as generation, and exact/near-duplicate rates describe accepted saved questions after production filtering, not the unexposed raw candidate stream.
