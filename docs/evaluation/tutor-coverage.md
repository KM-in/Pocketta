# Repeated tutor answer coverage

## Method

`backend/app/tools/evaluate_tutor_coverage.py` runs the six supported questions from the synthetic OS fixture through the production `TutorService` three times. It clears tutor conversation history before each question, so each case is evaluated independently. This measures whether the tutor returns an answer when the fixture contains evidence; it does not judge answer faithfulness, refusal quality, or learning outcomes. The full DeepEval run measures answer quality and unsupported-question refusal separately.

## Results

| Run | Answered attempts | Coverage | Notes |
|---|---:|---:|---|
| Initial history-reset run | 14/18 | 77.8% | Before the tutor prompt adjustment |
| After prompt adjustment | 17/18 | 94.4% | Five of six questions answered on every repeat; convoy effect answered twice |
| Full DeepEval run | 6/6 supported | 100% | Single run; both unsupported questions also correctly refused |

The repeated-run raw reports are [`tutor-coverage-2026-10-14.json`](tutor-coverage-2026-10-14.json) and [`tutor-coverage-remediated-2026-10-14.json`](tutor-coverage-remediated-2026-10-14.json). The latest three-repeat result suggests improved coverage after clarifying the tutor instruction to answer when reliable evidence directly supports the requested fact. The six-question sample remains small and responses are variable, so the one 6/6 run should not be presented as a guarantee.

Both generation and any LLM judging use Cerebras `qwen-3.8-27b`. The three-repeat coverage metric itself is a count of answered/refused responses, not an LLM score. Retrieval uses keyword mode because no embedding API key or local endpoint is configured in this checkout.

## Reproduce

From the repository root, with the backend environment and Cerebras configured:

```sh
python -m backend.app.tools.evaluate_tutor_coverage \
  --output docs/evaluation/tutor-coverage-2026-10-14.json
```

The run makes live model requests using only the synthetic OS fixture and may incur provider usage charges.
