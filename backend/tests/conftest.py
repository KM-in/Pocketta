"""Tests must never inherit developer credentials or the local .env file."""

import pytest

from backend.app.config import Settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
    # Keep ordinary tests offline and free of model downloads; local embedding
    # behavior is exercised explicitly in test_local_embeddings.py.
    monkeypatch.setenv("EMBEDDING_PROVIDER", "api")
