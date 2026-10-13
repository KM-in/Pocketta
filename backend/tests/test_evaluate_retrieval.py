import asyncio
from types import SimpleNamespace

import pytest

from backend.app.tools import evaluate_retrieval


def test_live_retrieval_evaluation_requires_an_embedding_configuration(monkeypatch):
    monkeypatch.setattr(
        evaluate_retrieval,
        "Settings",
        lambda **kwargs: SimpleNamespace(embedding_enabled=False),
    )

    with pytest.raises(RuntimeError, match="no embedding API key or local embedding endpoint"):
        asyncio.run(evaluate_retrieval.evaluate(live=True))
