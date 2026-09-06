"""Anthropic backend. Stays in code, off by default (LLM_PROVIDER=ollama, CLAUDE_DAILY_REQUESTS=0)."""

from __future__ import annotations

import base64
import time
from typing import Any

from ..config import settings
from .provider import LLMResult, ProviderUnavailable, QuotaExhausted, parse_json

PRICES = {"claude-sonnet-4-6": (3.0, 15.0), "claude-opus-4-1": (15.0, 75.0)}


class ClaudeProvider:
    name = "claude"

    def __init__(self, model: str, api_key: str | None = None, client: Any | None = None) -> None:
        self.model = model
        self.api_key = api_key if api_key is not None else settings.anthropic_api_key
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            if not self.api_key:
                raise ProviderUnavailable("ANTHROPIC_API_KEY is not set")
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def complete(self, system: str, user: str, *, json_schema: dict | None = None,
                 images: list[bytes] | None = None, max_tokens: int = 800) -> LLMResult:
        client = self.client
        content: list[dict[str, Any]] = []
        for img in images or []:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                         "data": base64.b64encode(img).decode()}})
        text_in = user if json_schema is None else user + "\nReply with only a JSON object matching this schema:\n" + str(json_schema)
        content.append({"type": "text", "text": text_in})
        t0 = time.perf_counter()
        try:
            resp = client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                          messages=[{"role": "user", "content": content}])
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "429" in msg or "rate_limit" in msg.lower():
                raise QuotaExhausted(f"claude {self.model}: {msg[:120]}") from exc
            raise ProviderUnavailable(f"claude {self.model}: {exc.__class__.__name__}: {msg[:120]}") from exc
        latency = (time.perf_counter() - t0) * 1000
        text = "".join(getattr(b, "text", "") for b in resp.content)
        usage = getattr(resp, "usage", None)
        tin, tout = int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0)
        pin, pout = PRICES.get(self.model, (3.0, 15.0))
        return LLMResult(text=text, parsed=parse_json(text) if json_schema is not None else None, tokens_in=tin,
                         tokens_out=tout, provider=self.name, model=self.model, latency_ms=latency,
                         cost_usd=(tin * pin + tout * pout) / 1e6)
