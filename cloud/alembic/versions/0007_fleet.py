"""edge_heartbeats.

Revision ID: 0007_fleet
Revises: 0006_notify
Create Date: 2026-09-06
"""

from __future__ import annotations

from sqlmodel import SQLModel

from alembic import op
from raqib_api import models  # noqa: F401

revision = "0007_fleet"
down_revision = "0006_notify"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.tables["edge_heartbeats"].create(bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table edge_heartbeats enable row level security")


def downgrade() -> None:
    SQLModel.metadata.tables["edge_heartbeats"].drop(op.get_bind(), checkfirst=True)
