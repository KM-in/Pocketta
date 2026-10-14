# Track D retrieval smoke result · 13 October 2026

## Method

Ran `python3 -m backend.app.tools.evaluate_retrieval` on the synthetic held-out OS fixture after switching to `main`. The harness creates a temporary SQLite course and indexes seven synthetic source units with keyword retrieval only; no external provider receives fixture text. It returns up to three evidence units per supported query. Precision is the fraction of returned content units at the fixture's expected source locations. Recall is the fraction of expected locations retrieved. Unsupported accuracy is the fraction of unsupported queries returning no evidence.

## Results

| Metric | Result |
|---|---:|
| Expected source locations retrieved | 6/6 (100%) |
| Mean context precision on supported questions | 0.639 |
| Mean context recall on supported questions | 1.000 |
| Unsupported queries with no evidence | 2/2 (100%) |

Per-query precision was 0.333, 0.500, 0.500, 0.500, 1.000, and 1.000; recall was 1.000 for all six supported queries. Both unsupported questions returned no evidence.

## Limits and next evaluation

This is a small synthetic keyword-retrieval smoke check. It does not measure semantic embeddings, answer faithfulness, answer relevancy, question correctness/ambiguity, repetition, or learning outcomes. It is not a RAGAS, DeepEval, or TruLens run. Separate integration checks now cover a configured provider, PDF image extraction, and synthetic video ingestion; see [the integration report](real-integration-checks.md). Live semantic retrieval still needs an embedding service, and context precision has room to improve. See [the Track D status](../HACKATHON_TRACK_D_STATUS.md) for remaining evaluation work.
