"""OpenTelemetry for every model call. One span per call with model, tokens, cost, latency and the prompt hash
(never the prompt). Exporter: none (in-process only), console, or OTLP/HTTP (OTEL_EXPORTER_OTLP_ENDPOINT).
Every span is also persisted to llm_spans, which is what the cost KPI sums."""

from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SimpleSpanProcessor,
)
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from .config import settings

log = logging.getLogger(__name__)
_provider: TracerProvider | None = None
memory_exporter = InMemorySpanExporter()  # always on: tests and the /cost endpoint's "spans today" cross-check


def setup() -> TracerProvider:
    global _provider
    if _provider is not None:
        return _provider
    prov = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
    prov.add_span_processor(SimpleSpanProcessor(memory_exporter))
    if settings.otel_exporter == "console":
        prov.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    elif settings.otel_exporter == "otlp" and settings.otel_exporter_otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        prov.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)))
    trace.set_tracer_provider(prov)
    _provider = prov
    return prov


def tracer():
    setup()
    return trace.get_tracer("raqib.llm")


def prompt_hash(system: str, user: str) -> str:
    return hashlib.sha256((system + "\n\x00\n" + user).encode()).hexdigest()[:16]


@contextmanager
def llm_span(task: str, site: str, system: str, user: str):
    """Usage: with llm_span(...) as span: ...; span.set_attribute(...). Attributes finish it."""
    with tracer().start_as_current_span(f"llm.{task}") as span:
        span.set_attribute("raqib.task", task)
        span.set_attribute("raqib.site", site)
        span.set_attribute("raqib.prompt_hash", prompt_hash(system, user))
        yield span


def record_span_row(task: str, site: str, res: Any, system: str, user: str, ok: bool = True) -> None:
    """Persist the ledger row. Never raises: a failing ledger write must not fail the model call."""
    try:
        from sqlmodel import Session

        from . import db as dbmod
        from .models import LlmSpan

        LlmSpan.__table__.create(dbmod.engine, checkfirst=True)
        with Session(dbmod.engine) as s:
            s.add(LlmSpan(site=site or "-", task=task, provider=getattr(res, "provider", "none"), model=getattr(res, "model", ""),
                          tokens_in=int(getattr(res, "tokens_in", 0) or 0), tokens_out=int(getattr(res, "tokens_out", 0) or 0),
                          cost_usd=float(getattr(res, "cost_usd", 0.0) or 0.0), latency_ms=float(getattr(res, "latency_ms", 0.0) or 0.0),
                          prompt_hash=prompt_hash(system, user), ok=ok, attempts=int(getattr(res, "attempts", 1) or 1)))
            s.commit()
    except Exception as exc:  # noqa: BLE001
        log.debug("llm span row not recorded: %s", exc)
