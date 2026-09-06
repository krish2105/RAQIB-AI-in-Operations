"""notify_optins (WhatsApp opt-in roster).

Revision ID: 0006_notify
Revises: 0005_pos
Create Date: 2026-09-06
"""

from __future__ import annotations

from sqlmodel import SQLModel

from alembic import op
from raqib_api import models  # noqa: F401

revision = "0006_notify"
down_revision = "0005_pos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.tables["notify_optins"].create(bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table notify_optins enable row level security")


def downgrade() -> None:
    SQLModel.metadata.tables["notify_optins"].drop(op.get_bind(), checkfirst=True)
