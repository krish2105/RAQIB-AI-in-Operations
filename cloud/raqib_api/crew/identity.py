"""Agent identities: name, role, tool allow-list, budget, signing key id."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field

from ..config import settings
from .budget import Budget


@dataclass(frozen=True)
class AgentIdentity:
    name: str
    role: str
    allowed_tools: frozenset[str]
    budget: Budget = field(default_factory=Budget.default)
    key_id: str = ""

    def __post_init__(self) -> None:
        if not self.key_id:
            object.__setattr__(self, "key_id", f"k-{self.name}")

    def signing_key(self) -> bytes:
        """Per-agent key derived from the crew secret; agents never share a key."""
        return hmac.new(settings.crew_hmac_secret.encode(), self.key_id.encode(), hashlib.sha256).digest()

    def may_call(self, tool: str) -> bool:
        return tool in self.allowed_tools
