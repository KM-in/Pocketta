# DeepEval Track D evaluation

## Status

The evaluator is implemented in `backend/app/tools/evaluate_track_d.py` and uses DeepEval 4.2.0. It creates a temporary course from `os-course.json`, indexes the synthetic excerpts using configured retrieval, asks the actual PocketTA `TutorService` the six supported questions, and measures DeepEval Faithfulness, Answer Relevancy, Contextual Precision, and Contextual Recall. It also checks whether the tutor refuses the two unsupported queries. The configured Cerebras model is used as the DeepEval judge.

The one-question live smoke run did **not** produce a tutor answer or metric scores. Cerebras returned HTTP 402 during generation, before DeepEval scoring began. Treat all four DeepEval metrics as **not measured** until a successful run writes a result JSON. This failure is evidence of unavailable provider credit, not a zero score.

## Reproduce

From the repository root, install the optional evaluator dependency in the backend environment:

```sh
python -m pip install -r backend/requirements.txt -r backend/requirements-eval.txt
```

Configure `MODEL_PROVIDER=cerebras` and a funded `CEREBRAS_API_KEY`. Embeddings are optional; when unavailable, the output explicitly records keyword retrieval. Run:

```sh
python -m backend.app.tools.evaluate_track_d \
  --output docs/evaluation/track-d-deepeval-2026-10-13.json
```

Use `--max-cases 1` for a small connection smoke run. The default evaluates all six supported fixture questions plus two unsupported questions. It makes real generation, verification, and judge requests, so it requires provider access and may incur usage charges. It sends only the synthetic OS fixture and evaluation prompts; no uploaded course material is used.

## Interpretation limits

The fixture contains synthetic short excerpts and six supported questions. The judge is the configured Cerebras model, so the results are model-based estimates, not human ratings. The four metrics assess answer grounding/relevance and retrieved context; they do not assess generated quiz correctness, ambiguity, learner gains, or exact-question repetition. The evaluator records the model identity, retrieval mode, per-case scores and judge reasons in the JSON result. Preserve that result with any submitted summary.
