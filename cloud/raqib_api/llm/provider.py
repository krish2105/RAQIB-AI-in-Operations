"""One interface for every model call, with a free fallback chain and strict-JSON handling.

    result = get_provider("route").complete(system, user, json_schema=PLAN_SCHEMA)
    plan = result.parsed or regex_fallback(user)     # parsed is None after one failed retry

Chain order comes from settings (`LLM_PROVIDER`, `LLM_PROVIDER_ORDER`, per-task overrides).
A provider that cannot be reached, has no key, or is out of quota raises and the chain moves
on. When every link fails the chain raises `ProviderUnavailable`; callers that must never
crash use `try_complete`, which returns None instead.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import jsonschema

from ..config import settings
from .quota import Quota

log = logging.getLogger(__name__)

Task = Literal["route", "answer", "caption", "opinion", "judge"]
TASKS: tuple[str, ...] = ("route", "answer", "caption", "opinion", "judge")


class LLMError(Exception):
    """Base class; never escapes `try_complete`."""


class ProviderUnavailable(LLMError):
    """No key, connection refused, timeout, unsupported input (e.g. images on a text-only provider)."""


class QuotaExhausted(LLMError):
    """The daily request cap for a provider is reached (ours or the provider's 429)."""


@dataclass
class LLMResult:
    text: str
    parsed: dict[str, Any] | None
    tokens_in: int
    tokens_out: int
    provider: str
    model: str
    latency_ms: float
    cost_usd: float = 0.0
    attempts: int = 1
    schema_error: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str, *, json_schema: dict | None = None,
                 images: list[bytes] | None = None, max_tokens: int = 800) -> LLMResult: ...


def parse_json(text: str) -> dict[str, Any] | None:
    """Tolerant JSON extraction: strips code fences and leading prose."""
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        out = json.loads(t[start:end + 1])
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) else None


class ProviderChain:
    """Tries providers in order; validates strict JSON with one retry; records quota; traces every call."""

    def __init__(self, task: str, providers: list[LLMProvider], quota: Quota | None = None, site: str = "-") -> None:
        self.task = task
        self.providers = providers
        self.quota = quota
        self.site = site
        self.name = "chain(" + ",".join(p.name for p in providers) + ")"

    def complete(self, system: str, user: str, *, json_schema: dict | None = None,
                 images: list[bytes] | None = None, max_tokens: int = 800) -> LLMResult:
        from ..telemetry import llm_span, record_span_row

        errors: list[str] = []
        with llm_span(self.task, self.site, system, user) as span:
            for p in self.providers:
                if self.quota is not None and not self.quota.check(p.name):
                    errors.append(f"{p.name}: quota exhausted")
                    continue
                try:
                    res = self._complete_with_schema(p, system, user, json_schema, images, max_tokens)
                except (ProviderUnavailable, QuotaExhausted) as exc:
                    errors.append(f"{p.name}: {exc}")
                    log.info("provider %s unavailable for %s: %s", p.name, self.task, exc)
                    continue
                if self.quota is not None:
                    self.quota.record(p.name, res.tokens_in + res.tokens_out, requests=res.attempts)
                span.set_attribute("raqib.provider", res.provider)
                span.set_attribute("raqib.model", res.model)
                span.set_attribute("raqib.tokens_in", res.tokens_in)
                span.set_attribute("raqib.tokens_out", res.tokens_out)
                span.set_attribute("raqib.cost_usd", res.cost_usd)
                span.set_attribute("raqib.latency_ms", res.latency_ms)
                span.set_attribute("raqib.attempts", res.attempts)
                record_span_row(self.task, self.site, res, system, user, ok=True)
                return res
            span.set_attribute("raqib.provider", "none")
            span.set_attribute("raqib.cost_usd", 0.0)
            span.set_attribute("raqib.error", "; ".join(errors)[:200])
        raise ProviderUnavailable(f"no provider for task {self.task!r}: " + "; ".join(errors))

    def _complete_with_schema(self, p: LLMProvider, system: str, user: str, schema: dict | None,
                              images: list[bytes] | None, max_tokens: int) -> LLMResult:
        res = p.complete(system, user, json_schema=schema, images=images, max_tokens=max_tokens)
        if schema is None:
            return res
        err = _validate(res, schema)
        if err is None:
            return res
        retry_user = (user + "\n\nYour previous reply was rejected: " + err
                      + "\nReply with only a JSON object that matches the schema. No prose.")
        res2 = p.complete(system, retry_user, json_schema=schema, images=images, max_tokens=max_tokens)
        res2.attempts = 2
        res2.tokens_in += res.tokens_in
        res2.tokens_out += res.tokens_out
        res2.latency_ms += res.latency_ms
        err2 = _validate(res2, schema)
        if err2 is not None:
            res2.parsed = None
            res2.schema_error = err2
            log.warning("%s returned invalid JSON twice for %s: %s", p.name, self.task, err2)
        return res2


def _validate(res: LLMResult, schema: dict) -> str | None:
    if res.parsed is None:
        res.parsed = parse_json(res.text)
    if res.parsed is None:
        return "no JSON object found"
    try:
        jsonschema.validate(res.parsed, schema)
    except jsonschema.ValidationError as exc:
        res.parsed = None
        return f"{exc.message} at {list(exc.absolute_path)}"
    return None


# ---- factory ----------------------------------------------------------------------------

def _order_for(task: str) -> list[str]:
    override = getattr(settings, f"llm_provider_{task}", None)
    if override:
        return [x.strip() for x in override.split(",") if x.strip()]
    first = settings.llm_provider.strip()
    if first == "claude":
        return ["claude"]
    order = [x.strip() for x in settings.llm_provider_order.split(",") if x.strip()]
    if first in order:
        order.remove(first)
    return [first, *order]


def _build(name: str, task: str) -> LLMProvider | None:
    if name == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider(model=getattr(settings, f"ollama_model_{task}"))
    if name == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(model=settings.gemini_model_route if task == "route" else settings.gemini_model_text)
    if name == "groq":
        from .groq import GroqProvider

        return GroqProvider(model=settings.groq_model)
    if name == "claude":
        from .claude import ClaudeProvider

        return ClaudeProvider(model=settings.agent_model)
    log.warning("unknown LLM provider %r ignored", name)
    return None


def get_provider(task: Task, *, quota: Quota | None = None, providers: list[LLMProvider] | None = None, site: str = "-") -> ProviderChain:
    """Chain for `task`. Reads LLM_PROVIDER and per-task overrides; falls through the free order."""
    if task not in TASKS:
        raise ValueError(f"unknown task {task!r}; expected one of {TASKS}")
    if providers is None:
        providers = [p for p in (_build(n, task) for n in _order_for(task)) if p is not None]
    return ProviderChain(task, providers, quota if quota is not None else Quota.default(), site=site)


def try_complete(chain: ProviderChain, system: str, user: str, **kw: Any) -> LLMResult | None:
    """Degrade, never crash: None when no provider could answer."""
    try:
        return chain.complete(system, user, **kw)
    except LLMError as exc:
        log.warning("llm unavailable for %s: %s", chain.task, exc)
        return None
