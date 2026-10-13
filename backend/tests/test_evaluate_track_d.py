import pytest

deepeval = pytest.importorskip("deepeval")

import httpx
from pydantic import BaseModel

from backend.app.config import Settings
from backend.app.services.gateway import strict_schema
from backend.app.tools.evaluate_track_d import CerebrasJudge


class JudgeOutput(BaseModel):
    ok: bool


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": '{"ok":true}'}}]}


def test_cerebras_judge_sync_request_uses_configured_adapter(monkeypatch):
    captured = {}

    def fake_post(self, url, *, headers, json):
        captured.update(url=url, headers=headers, json=json)
        return FakeResponse()

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    settings = Settings(
        _env_file=None,
        model_provider="cerebras",
        cerebras_base_url="https://judge.example/v1",
        cerebras_api_key="test-secret",
        cerebras_text_model="judge-model",
        cerebras_completion_token_field="max_tokens",
    )

    judge = CerebrasJudge(settings)
    assert judge.generate("score this", schema=JudgeOutput) == '{"ok":true}'
    assert captured["url"] == "https://judge.example/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer test-secret"}
    assert captured["json"]["response_format"]["json_schema"]["schema"] == strict_schema(
        JudgeOutput.model_json_schema()
    )
    assert captured["json"]["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_cerebras_judge_async_request_uses_configured_adapter(monkeypatch):
    captured = {}

    async def fake_post(self, url, *, headers, json):
        captured.update(url=url, headers=headers, json=json)
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    settings = Settings(
        _env_file=None,
        model_provider="cerebras",
        cerebras_api_key="test-secret",
        cerebras_text_model="judge-model",
        cerebras_completion_token_field="max_completion_tokens",
    )

    judge = CerebrasJudge(settings)
    assert await judge.a_generate("score this") == '{"ok":true}'
    assert captured["json"]["max_completion_tokens"] == 2048
    assert "max_tokens" not in captured["json"]
