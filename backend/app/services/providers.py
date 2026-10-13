"""Provider configuration and request coordination, shared by the application."""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime


@dataclass(frozen=True)
class ProviderAdapter:
    name: str
    base_url: str
    api_key: str
    completion_token_field: str = "max_tokens"

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def chat_payload(self, payload):
        result = dict(payload)
        if self.completion_token_field != "max_tokens":
            result[self.completion_token_field] = result.pop("max_tokens", 4096)
        return result


def text_adapter(settings):
    if settings.model_provider == "cerebras":
        return ProviderAdapter(
            "cerebras",
            settings.cerebras_base_url,
            settings.cerebras_api_key,
            settings.cerebras_completion_token_field,
        )
    return ProviderAdapter(
        "lm_studio", settings.lm_studio_base_url, settings.lm_studio_api_key
    )


class RequestCoordinator:
    def __init__(self, settings):
        self.concurrency = settings.provider_concurrency
        self.interval = settings.provider_request_interval_seconds
        self.semaphores = {}
        self.locks = {}
        self.next_allowed = {}

    @asynccontextmanager
    async def slot(self, provider):
        semaphore = self.semaphores.setdefault(
            provider, asyncio.Semaphore(self.concurrency)
        )
        async with semaphore:
            lock = self.locks.setdefault(provider, asyncio.Lock())
            async with lock:
                # Recheck after waking: another request may have extended cooldown.
                while (
                    delay := self.next_allowed.get(provider, 0) - time.monotonic()
                ) > 0:
                    await asyncio.sleep(delay)
                self.next_allowed[provider] = time.monotonic() + self.interval
            yield

    def cooldown(self, provider, value, fallback):
        delay = fallback
        if value:
            try:
                delay = max(0, float(value))
            except ValueError:
                try:
                    delay = max(
                        0,
                        (
                            parsedate_to_datetime(value) - datetime.now(UTC)
                        ).total_seconds(),
                    )
                except (TypeError, ValueError, OverflowError):
                    pass
        self.next_allowed[provider] = max(
            self.next_allowed.get(provider, 0), time.monotonic() + delay
        )
        return delay
