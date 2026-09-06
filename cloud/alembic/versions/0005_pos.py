"""pos_transactions.

Revision ID: 0005_pos
Revises: 0004_crew
Create Date: 2026-09-06
"""

from __future__ import annotations

from sqlmodel import SQLModel

from alembic import op
from raqib_api import models  # noqa: F401

revision = "0005_pos"
down_revision = "0004_crew"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.tables["pos_transactions"].create(bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table pos_transactions enable row level security")


def downgrade() -> None:
    SQLModel.metadata.tables["pos_transactions"].drop(op.get_bind(), checkfirst=True)
