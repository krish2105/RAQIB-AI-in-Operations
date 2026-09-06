"""Groq free tier: fast text fallback. No vision; images raise ProviderUnavailable so the chain moves on."""

from __future__ import annotations

import time
from typing import Any

from ..config import settings
from .provider import LLMResult, ProviderUnavailable, QuotaExhausted, parse_json


class GroqProvider:
    name = "groq"

    def __init__(self, model: str, api_key: str | None = None, client: Any | None = None) -> None:
        self.model = model
        self.api_key = api_key if api_key is not None else settings.groq_api_key
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise ProviderUnavailable("GROQ_API_KEY is not set")
            import groq

            self._client = groq.Groq(api_key=self.api_key, timeout=settings.llm_timeout_s)
        return self._client

    def complete(self, system: str, user: str, *, json_schema: dict | None = None,
                 images: list[bytes] | None = None, max_tokens: int = 800) -> LLMResult:
        if images:
            raise ProviderUnavailable("groq text models do not accept images")
        client = self.client
        kwargs: dict[str, Any] = {
            "model": self.model, "max_tokens": max_tokens, "temperature": 0.1,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if json_schema is not None:
            kwargs["response_format"] = {"type": "json_object"}
        t0 = time.perf_counter()
        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "429" in msg or "rate_limit" in msg.lower():
                raise QuotaExhausted(f"groq {self.model}: {msg[:120]}") from exc
            raise ProviderUnavailable(f"groq {self.model}: {exc.__class__.__name__}: {msg[:120]}") from exc
        latency = (time.perf_counter() - t0) * 1000
        text = resp.choices[0].message.content or "" if getattr(resp, "choices", None) else ""
        usage = getattr(resp, "usage", None)
        return LLMResult(text=text, parsed=parse_json(text) if json_schema is not None else None,
                         tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
                         tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
                         provider=self.name, model=self.model, latency_ms=latency, cost_usd=0.0)
