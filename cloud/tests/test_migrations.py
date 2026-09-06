"""Alembic migration 0001 applies up and down on a temporary SQLite database."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command
from raqib_api import models

CLOUD = Path(__file__).resolve().parents[1]


def _cfg(url: str) -> Config:
    cfg = Config(str(CLOUD / "alembic.ini"))
    cfg.set_main_option("script_location", str(CLOUD / "alembic"))
    cfg.cmd_opts = type("o", (), {"x": [f"url={url}"]})()  # -x url=...
    return cfg


def test_upgrade_and_downgrade_on_temp_db(tmp_path):
    url = f"sqlite:///{tmp_path / 'mig.db'}"
    cfg = _cfg(url)
    command.upgrade(cfg, "head")
    names = set(inspect(create_engine(url)).get_table_names())
    for t in models.V2_TABLES:
        assert t in names, f"{t} missing after upgrade"
    assert "events" in names  # baseline created on a fresh DB
    command.downgrade(cfg, "base")
    names = set(inspect(create_engine(url)).get_table_names())
    for t in models.V2_TABLES:
        assert t not in names, f"{t} still present after downgrade"
    assert "events" in names  # never touches Phase A–D tables


def test_chunk_embedding_round_trips_on_sqlite(tmp_path):
    from sqlmodel import Session, SQLModel
    from sqlmodel import create_engine as ce

    eng = ce(f"sqlite:///{tmp_path / 'c.db'}")
    SQLModel.metadata.create_all(eng)
    vec = [0.1] * 8
    with Session(eng) as s:
        s.add(models.Chunk(id="01J" + "0" * 23, site="raqib_demo_store", kind="event", text="hello", embedding=vec, model="test"))
        s.commit()
        row = s.get(models.Chunk, "01J" + "0" * 23)
        assert row.embedding == vec and row.model == "test"


def test_v2_models_do_not_alter_phase_ad_columns():
    cols = {c.name for c in models.Event.__table__.columns}
    assert cols == {"id", "site", "camera", "ts", "kind", "severity", "payload", "clip_path", "rule_id", "received_at", "handled"}
