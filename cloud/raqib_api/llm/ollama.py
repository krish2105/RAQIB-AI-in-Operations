"""Local Ollama (the M4 Pro in dev, the edge box in production). Free, private, no quota."""

from __future__ import annotations

import time
from typing import Any

from ..config import settings
from .provider import LLMResult, ProviderUnavailable, parse_json


class OllamaProvider:
    name = "ollama"

    def __init__(self, model: str, host: str | None = None, client: Any | None = None, timeout: float | None = None) -> None:
        self.model = model
        self.host = host or settings.ollama_host
        self._client = client
        self.timeout = timeout or settings.llm_timeout_s

    @property
    def client(self) -> Any:
        if self._client is None:
            import ollama

            self._client = ollama.Client(host=self.host, timeout=self.timeout)
        return self._client

    def complete(self, system: str, user: str, *, json_schema: dict | None = None,
                 images: list[bytes] | None = None, max_tokens: int = 800) -> LLMResult:
        msg: dict[str, Any] = {"role": "user", "content": user}
        if images:
            msg["images"] = list(images)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, msg],
            "options": {"num_predict": max_tokens, "temperature": 0.1},
            "stream": False,
        }
        if json_schema is not None:
            kwargs["format"] = json_schema
        if self.model.startswith("qwen3"):
            kwargs["think"] = False
        t0 = time.perf_counter()
        try:
            resp = self.client.chat(**kwargs)
        except Exception as exc:  # noqa: BLE001 — connection refused, model missing, timeout
            raise ProviderUnavailable(f"ollama {self.model} at {self.host}: {exc.__class__.__name__}: {exc}") from exc
        latency = (time.perf_counter() - t0) * 1000
        text = _get(resp, "message", "content") or ""
        return LLMResult(text=text, parsed=parse_json(text) if json_schema is not None else None,
                         tokens_in=int(_get(resp, "prompt_eval_count") or 0), tokens_out=int(_get(resp, "eval_count") or 0),
                         provider=self.name, model=self.model, latency_ms=latency, cost_usd=0.0)


def _get(obj: Any, *path: str) -> Any:
    for k in path:
        if obj is None:
            return None
        obj = obj.get(k) if isinstance(obj, dict) else getattr(obj, k, None)
    return obj
