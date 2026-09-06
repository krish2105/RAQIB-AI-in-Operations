"""Gemini free tier (text + vision) via google-genai. Used when the edge Ollama is unreachable."""

from __future__ import annotations

import time
from typing import Any

from ..config import settings
from .provider import LLMResult, ProviderUnavailable, QuotaExhausted, parse_json


class GeminiProvider:
    name = "gemini"

    def __init__(self, model: str, api_key: str | None = None, client: Any | None = None) -> None:
        self.model = model
        self.api_key = api_key if api_key is not None else settings.gemini_api_key
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise ProviderUnavailable("GEMINI_API_KEY is not set")
            from google import genai

            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def complete(self, system: str, user: str, *, json_schema: dict | None = None,
                 images: list[bytes] | None = None, max_tokens: int = 800) -> LLMResult:
        client = self.client
        from google.genai import types

        parts: list[Any] = [user]
        for img in images or []:
            parts.append(types.Part.from_bytes(data=img, mime_type="image/jpeg"))
        config: dict[str, Any] = {"system_instruction": system, "max_output_tokens": max_tokens, "temperature": 0.1}
        if json_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_json_schema"] = json_schema
        t0 = time.perf_counter()
        try:
            resp = client.models.generate_content(model=self.model, contents=parts, config=config)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
                raise QuotaExhausted(f"gemini {self.model}: {msg[:120]}") from exc
            raise ProviderUnavailable(f"gemini {self.model}: {exc.__class__.__name__}: {msg[:120]}") from exc
        latency = (time.perf_counter() - t0) * 1000
        text = getattr(resp, "text", None) or ""
        usage = getattr(resp, "usage_metadata", None)
        return LLMResult(text=text, parsed=parse_json(text) if json_schema is not None else None,
                         tokens_in=int(getattr(usage, "prompt_token_count", 0) or 0),
                         tokens_out=int(getattr(usage, "candidates_token_count", 0) or 0),
                         provider=self.name, model=self.model, latency_ms=latency, cost_usd=0.0)
