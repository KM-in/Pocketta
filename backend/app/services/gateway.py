from __future__ import annotations
import asyncio
import base64
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
import httpx
from pydantic import BaseModel
from .lm_studio import LMStudioService


class VisionResult(BaseModel):
    transcription: str
    description: str
    uncertain: bool


def strict_schema(schema):
    if isinstance(schema, dict):
        schema = {k: strict_schema(v) for k, v in schema.items() if k != "default"}
        if schema.get("type") == "object":
            schema["additionalProperties"] = False
            schema["required"] = list(schema.get("properties", {}))
    elif isinstance(schema, list):
        schema = [strict_schema(v) for v in schema]
    return schema


class ModelGateway(LMStudioService):
    """Reuse grounded generation orchestration with a provider-independent transport."""

    def __init__(self, settings, database, source_id=None):
        super().__init__(settings)
        self.database = database
        self.source_id = source_id

    async def generate(self, transcript):
        if self.settings.model_provider == "lm_studio":
            return await super().generate(transcript)
        # The legacy orchestrator checks this setting; model transport uses Cerebras settings.
        original = self.settings
        self.settings = original.model_copy(
            update={"lm_studio_model_id": original.cerebras_text_model}
        )
        try:
            return await super().generate(transcript)
        finally:
            self.settings = original

    async def generate_structured(self, prompt: str, schema: type[BaseModel]) -> dict:
        """Generate and validate against a Pydantic schema on either provider."""
        result = await self._generate_model(schema, prompt, max_tokens=4096)
        return result.model_dump()

    async def analyse_image(self, image_path: Path, prompt: str):
        if self.settings.model_provider != "cerebras":
            raise ValueError("Document vision requires MODEL_PROVIDER=cerebras")
        encoded = base64.b64encode(image_path.read_bytes()).decode()
        if len(encoded) > 9 * 1024 * 1024:
            raise ValueError("Rendered page exceeds vision request limit")
        payload = {
            "model": self.settings.cerebras_vision_model,
            "max_completion_tokens": 4096,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "vision",
                    "strict": True,
                    "schema": VisionResult.model_json_schema(),
                },
            },
        }
        return VisionResult.model_validate_json(await self._request(payload, "vision"))

    async def _complete(self, payload):
        if self.settings.model_provider == "lm_studio":
            started, outcome = time.perf_counter(), "failed"
            try:
                result = await super()._complete(payload)
                outcome = "completed"
                return result
            finally:
                self.record_run(
                    "lm_studio",
                    self.settings.lm_studio_model_id,
                    "structured",
                    started,
                    {},
                    outcome,
                )
        payload = dict(payload)
        payload["model"] = self.settings.cerebras_text_model
        payload["max_completion_tokens"] = payload.pop("max_tokens", 4096)
        payload["messages"][0][
            "content"
        ] = "You are a grounded course study assistant. Use only supplied evidence. Cite exact supplied content-unit IDs in segment_ids; never produce page numbers. Return the requested JSON schema."
        return await self._request(payload, "study_pack")

    async def _request(self, payload, feature):
        if not self.settings.cerebras_api_key:
            raise ValueError(
                "Set CEREBRAS_API_KEY on the server to enable cloud processing"
            )
        if "response_format" in payload:
            spec = payload["response_format"]["json_schema"]
            spec["schema"] = strict_schema(spec["schema"])
        started = time.perf_counter()
        usage, outcome = {}, "failed"
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.lm_studio_timeout_seconds, trust_env=False
            ) as client:
                for attempt in range(3):
                    try:
                        response = await client.post(
                            "https://api.cerebras.ai/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {self.settings.cerebras_api_key}"
                            },
                            json=payload,
                        )
                    except httpx.HTTPError:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(2**attempt)
                        continue
                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < 2:
                            await asyncio.sleep(2**attempt)
                            continue
                    if response.is_error:
                        raise ValueError(
                            f"Cerebras request failed (HTTP {response.status_code}); check provider configuration or retry"
                        )
                    body = response.json()
                    usage = body.get("usage", {})
                    outcome = "completed"
                    return body["choices"][0]["message"]["content"]
        except httpx.HTTPError as error:
            raise ValueError(
                "Cerebras connection failed; check connectivity and retry"
            ) from error
        finally:
            self.record_run(
                "cerebras", payload["model"], feature, started, usage, outcome
            )

    def record_run(self, provider, model, feature, started, usage, outcome):
        with self.database._connect() as c:
            c.execute(
                "INSERT INTO model_runs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    str(uuid.uuid4()),
                    self.source_id,
                    provider,
                    model,
                    feature,
                    "course-v1",
                    time.perf_counter() - started,
                    json.dumps(usage),
                    outcome,
                    datetime.now(UTC).isoformat(),
                ),
            )
