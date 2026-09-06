"""ask_log: every /ask call with plan, citations and cost.

Revision ID: 0002_ask_log
Revises: 0001_v2
Create Date: 2026-09-06
"""

from __future__ import annotations

from sqlmodel import SQLModel

from alembic import op
from raqib_api import models  # noqa: F401

revision = "0002_ask_log"
down_revision = "0001_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.tables["ask_log"].create(bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table ask_log enable row level security")


def downgrade() -> None:
    SQLModel.metadata.tables["ask_log"].drop(op.get_bind(), checkfirst=True)
