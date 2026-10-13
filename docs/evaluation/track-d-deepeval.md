# DeepEval Track D evaluation

## Status

The evaluator uses DeepEval 4.2.0 and runs the actual PocketTA tutor over the six supported and two unsupported questions in `os-course.json`. A live run completed on 14 October 2026 using Cerebras `qwen-3.8-27b` for tutor generation and as the LLM judge. The result is saved in [`track-d-deepeval-2026-10-14.json`](track-d-deepeval-2026-10-14.json).

| Measure | Result | Cases |
|---|---:|---:|
| Tutor faithfulness | 1.000 | 6 answered supported questions |
| Answer relevancy | 0.972 | 6 answered supported questions |
| Context precision | 0.972 | 6 supported questions |
| Context recall | 1.000 | 6 supported questions |
| Tutor answer coverage | 6/6 (100%) | 6 supported questions |
| Unsupported-question refusal accuracy | 2/2 (100%) | 2 unsupported questions |

The evaluator clears tutor conversation history before every independent fixture question. On this run it answered all six supported questions and refused both unsupported ones. A separate three-repeat coverage evaluation, also resetting tutor history per question, answered 17 of 18 supported attempts (94.4%); the convoy-effect question was answered in two of three attempts. See [the repeated coverage report](tutor-coverage.md) and its raw JSON results. The evaluator reports answer coverage separately so refusals do not distort answer-quality averages. Retrieval metrics cover all six supported questions. Earlier 402 and sandbox DNS failures were resolved; live Cerebras tutoring and judging now succeed.

## Reproduce

From the repository root, install the optional evaluator dependency in the backend environment:

```sh
python -m pip install -r backend/requirements.txt -r backend/requirements-eval.txt
```

Configure `MODEL_PROVIDER=cerebras` and a funded `CEREBRAS_API_KEY`. Embeddings are optional; when unavailable, the output explicitly records keyword retrieval. Run:

```sh
python -m backend.app.tools.evaluate_track_d \
  --output docs/evaluation/track-d-deepeval-2026-10-14.json
```

Use `--max-cases 1` for a small connection smoke run. The default evaluates all six supported fixture questions plus two unsupported questions. It makes real generation, verification, and judge requests, so it requires provider access and may incur usage charges. It sends only the synthetic OS fixture and evaluation prompts; no uploaded course material is used.

## Interpretation limits

The fixture contains synthetic short excerpts and six supported questions. The same configured Cerebras model is used for generation and judging, so these are model-based estimates, not independent human ratings. The samples are small and coverage varied across runs (6/6 once; 17/18 across three repeats), so the single full-run result is not a guarantee of consistent responses. The metrics do not assess generated quiz correctness, ambiguity, learner gains, or exact-question repetition. Preserve the JSON result and report scores, coverage, and these limits in any submission summary.
