import asyncio
import sys
from types import ModuleType, SimpleNamespace

from backend.app.config import Settings
from backend.app.services.gateway import ModelGateway


def test_fastembed_backend_uses_passage_prefix_and_data_cache(monkeypatch, tmp_path):
    captured = {}

    class FakeEmbedding:
        def __init__(self, *, model_name, cache_dir):
            captured["init"] = (model_name, cache_dir)

        def embed(self, texts):
            captured["texts"] = texts
            return iter([[0.25, 0.75] for _ in texts])

    monkeypatch.setitem(sys.modules, "fastembed", ModuleType("fastembed"))
    sys.modules["fastembed"].TextEmbedding = FakeEmbedding
    ModelGateway._fastembed_models.clear()
    gateway = ModelGateway.__new__(ModelGateway)
    gateway.settings = SimpleNamespace(
        fastembed_model="BAAI/bge-small-en-v1.5",
        fastembed_cache_path=tmp_path / "fastembed",
    )

    assert gateway._embed_fastembed(["source passage", "query: a query"]) == [
        [0.25, 0.75],
        [0.25, 0.75],
    ]
    assert captured["init"] == (
        "BAAI/bge-small-en-v1.5",
        str(tmp_path / "fastembed"),
    )
    assert captured["texts"] == ["passage: source passage", "query: a query"]


def test_fastembed_configuration_has_distinct_identity_and_enables_indexing():
    settings = Settings(
        _env_file=None,
        embedding_provider="fastembed",
        fastembed_model="BAAI/bge-small-en-v1.5",
        openai_api_key="",
    )
    assert settings.embedding_enabled
    assert settings.embedding_identity == "fastembed|BAAI/bge-small-en-v1.5"


def test_api_key_does_not_switch_default_away_from_free_local_embeddings(monkeypatch):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    settings = Settings(_env_file=None, openai_api_key="configured-but-unused")
    assert settings.embedding_provider == "fastembed"
    assert settings.embedding_enabled
    assert settings.embedding_identity.startswith("fastembed|")


def test_default_embedding_call_does_not_use_http_even_with_api_key(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)

    class FakeEmbedding:
        def __init__(self, **kwargs):
            pass

        def embed(self, texts):
            return iter([[1.0, 0.0] for _ in texts])

    module = ModuleType("fastembed")
    module.TextEmbedding = FakeEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", module)
    ModelGateway._fastembed_models.clear()
    settings = Settings(
        _env_file=None,
        openai_api_key="configured-but-unused",
        pocketta_data_dir=tmp_path,
    )
    gateway = ModelGateway.__new__(ModelGateway)
    gateway.settings = settings

    async def unexpected_http(*args, **kwargs):
        raise AssertionError("default local embeddings must not send API requests")

    gateway._request = unexpected_http
    assert asyncio.run(gateway.embed(["private course text"])) == [[1.0, 0.0]]
