import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite://")  # in-memory unless overridden per test
os.environ.setdefault("AGENT_BACKEND", "dryrun")
os.environ["ANTHROPIC_API_KEY"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient bound to a fresh on-disk SQLite so threads share state."""
    from sqlalchemy.pool import StaticPool
    from sqlmodel import SQLModel, create_engine

    from raqib_api import db as dbmod
    from raqib_api.config import settings

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(dbmod, "engine", eng)
    monkeypatch.setattr(settings, "clips_dir", str(tmp_path / "clips"))
    from raqib_api import models  # noqa: F401

    SQLModel.metadata.create_all(eng)
    from fastapi.testclient import TestClient

    from raqib_api.main import app

    with TestClient(app) as c:
        yield c


def make_event(i: int = 0, *, kind="footfall_tick", severity=1, payload=None, site="raqib_demo_store",
               ts: datetime | None = None, camera="cam1", rule="R12"):
    from ulid import ULID

    ts = ts or (datetime(2026, 9, 6, 9, 0, tzinfo=UTC) + timedelta(seconds=i))
    return {
        "id": str(ULID.from_timestamp(ts.timestamp() + i * 0.001)),
        "site": site, "camera": camera, "ts": ts.isoformat(), "kind": kind, "severity": severity,
        "payload": payload or {}, "clip_path": None, "rule_id": rule,
    }
