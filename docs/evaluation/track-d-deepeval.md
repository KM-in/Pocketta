# DeepEval Track D evaluation

## Status

The evaluator uses DeepEval 4.2.0 and runs the actual PocketTA tutor over the six supported and two unsupported questions in `os-course.json`. A live run completed on 14 October 2026 using Cerebras `qwen-3.8-27b` for tutor generation and as the LLM judge. The result is saved in [`track-d-deepeval-2026-10-14.json`](track-d-deepeval-2026-10-14.json).

| Measure | Result | Cases |
|---|---:|---:|
| Tutor faithfulness | 1.000 | 4 answered supported questions |
| Answer relevancy | 0.969 | 4 answered supported questions |
| Context precision | 0.972 | 6 supported questions |
| Context recall | 1.000 | 6 supported questions |
| Tutor answer coverage | 4/6 (66.7%) | 6 supported questions |
| Unsupported-question refusal accuracy | 2/2 (100%) | 2 unsupported questions |

In the full run, the tutor refused two questions that the fixture marks as answerable: process address space and thread sharing. A separate isolated replay of the process-address-space question returned an answer with claims that passed semantic verification, so the 4/6 coverage result is a single-run observation and response stability still needs repeated measurement. The evaluator reports answer coverage separately so a refusal cannot inflate faithfulness or lower answer relevancy as if it were an attempted answer. Retrieval metrics still include all six supported questions. The earlier 402 and a sandbox DNS failure were followed by a successful live run after the judge adapter was changed to normalize schemas like the production gateway.

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

The fixture contains synthetic short excerpts and six supported questions. The same configured Cerebras model is used for generation and judging, so these are model-based estimates, not independent human ratings. The strong scores apply to only four answers; the 4/6 answer coverage and two false refusals are material limits. The metrics do not assess generated quiz correctness, ambiguity, learner gains, or exact-question repetition. Preserve the JSON result and report both scores and coverage in any submission summary.
