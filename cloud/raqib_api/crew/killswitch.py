"""Global kill switch: env AGENTS_ENABLED and the crew_flags row `agents_enabled`, both checked before every run."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session

from ..config import settings
from ..models import CrewFlag

KEY = "agents_enabled"


class AgentsDisabled(RuntimeError):
    pass


def enabled(session: Session) -> bool:
    if not settings.agents_enabled:
        return False
    row = session.get(CrewFlag, KEY)
    return row is None or row.value.lower() == "true"


def set_enabled(session: Session, value: bool, by: str, note: str = "") -> CrewFlag:
    row = session.get(CrewFlag, KEY) or CrewFlag(key=KEY)
    row.value, row.updated_by, row.note, row.updated_at = ("true" if value else "false"), by, note, datetime.now(UTC)
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def check(session: Session) -> None:
    if not enabled(session):
        raise AgentsDisabled("agents are disabled (kill switch)")
