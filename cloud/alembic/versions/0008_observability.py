"""llm_spans and retention_log.

Revision ID: 0008_obs
Revises: 0007_fleet
Create Date: 2026-09-06
"""

from __future__ import annotations

from sqlmodel import SQLModel

from alembic import op
from raqib_api import models  # noqa: F401

revision = "0008_obs"
down_revision = "0007_fleet"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    for t in ("llm_spans", "retention_log"):
        SQLModel.metadata.tables[t].create(bind, checkfirst=True)
        if bind.dialect.name == "postgresql":
            op.execute(f"alter table {t} enable row level security")


def downgrade() -> None:
    bind = op.get_bind()
    for t in ("retention_log", "llm_spans"):
        SQLModel.metadata.tables[t].drop(bind, checkfirst=True)
