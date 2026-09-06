"""Roles and site scoping. The matrix lives in docs/rbac.md and in `ROUTE_MIN_ROLE` below."""

from __future__ import annotations

from dataclasses import dataclass, field

ROLES = ("viewer", "operator", "manager", "admin")
RANK = {r: i for i, r in enumerate(ROLES)}

# minimum role per capability; every route maps to one of these
CAPABILITIES = {
    "read": "viewer",
    "ask": "viewer",
    "approve": "operator",  # approve / reject proposals, request opinions, opt-ins
    "ingest": "operator",  # events/clips/detections from the edge box (service account)
    "manage": "manager",  # seed, index, documents, POS import, memory snapshots, pin memories
    "policy": "admin",  # policy thresholds, kill switch, users and roles
}


@dataclass(frozen=True)
class Principal:
    id: str
    email: str
    role: str = "viewer"
    site_ids: tuple[str, ...] = field(default_factory=tuple)  # empty = every site
    anonymous: bool = False

    def at_least(self, role: str) -> bool:
        return RANK.get(self.role, -1) >= RANK[role]

    def can(self, capability: str) -> bool:
        return self.at_least(CAPABILITIES[capability])

    def may_see(self, site: str | None) -> bool:
        return not self.site_ids or site is None or site in self.site_ids


DEV_ADMIN = Principal(id="dev", email="dev@local", role="admin", anonymous=True)
