from __future__ import annotations
import httpx
from ..config import Settings
from .generation import (
    GenerationService,
    GenerationError,
    ChunkSummary,
    _chunk_segments,
    _extract_content,
    _extract_json_object,
    _source_supports_full_pack,
)

LMStudioError = GenerationError


class LMStudioService(GenerationService):
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def text_model(self):
        return self.settings.lm_studio_model_id

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.lm_studio_api_key:
            headers["Authorization"] = f"Bearer {self.settings.lm_studio_api_key}"
        return headers

    async def available_models(self) -> list[str]:
        async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
            response = await client.get(
                f"{self.settings.lm_studio_base_url.rstrip('/')}/models",
                headers=self.headers,
            )
            response.raise_for_status()
        return [
            str(item["id"])
            for item in response.json().get("data", [])
            if item.get("id")
        ]

    async def _complete(self, payload: dict) -> str:
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.generation_timeout_seconds, trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.settings.lm_studio_base_url.rstrip('/')}/chat/completions",
                    headers=self.headers,
                    json=payload,
                )
                response.raise_for_status()
            return _extract_content(response.json())
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            detail = str(error).strip() or error.__class__.__name__
            raise LMStudioError(f"LM Studio request failed: {detail}") from error
