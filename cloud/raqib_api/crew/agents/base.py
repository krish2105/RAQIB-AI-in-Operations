"""Shared bits for the six agents: identity, optional zero-cost rationale, evidence helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlmodel import Session

from ...llm import get_provider, try_complete
from ...models import Event
from ..identity import AgentIdentity
from ..memory import memory_block, recall

PROMPTS = Path(__file__).resolve().parents[2] / "prompts" / "crew"


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


def rationale(agent: str, facts: str, fallback: str, lang: str = "en") -> str:
    """Optional model-written rationale (free provider); the deterministic fallback is always ready."""
    res = try_complete(get_provider("answer"), prompt(agent), f"Language: {lang}\nFacts (data): {facts}\nWrite the rationale.", max_tokens=160)
    text = (res.text or "").strip() if res else ""
    return text if 20 <= len(text) <= 600 and "<" not in text else fallback


def memories_for(identity: AgentIdentity, site: str, session: Session) -> str:
    return memory_block(recall(site, identity.name, session, limit=8))


def event_evidence(event: Event | None) -> list[str]:
    return [f"event:{event.id}"] if event else []


def precedent(site: str, q: str, session: Session, k: int = 3) -> tuple[str, list[str]]:
    """Ask-retrieved precedent for a decision: a short line and chunk-id citations. Empty when nothing is indexed."""
    try:
        from datetime import UTC, datetime

        from ...rag.retriever import retrieve
        from ...rag.router_query import parse_regex

        plan = parse_regex(q, datetime.now(UTC))
        hits = retrieve(plan, site, session, k=k)
    except Exception:  # noqa: BLE001
        return "", []
    if not hits:
        return "", []
    return "; ".join(h.text[:120] for h in hits), [f"chunk:{h.chunk_id}" for h in hits]


__all__ = ["AgentIdentity", "event_evidence", "memories_for", "precedent", "prompt", "rationale", "Any"]
