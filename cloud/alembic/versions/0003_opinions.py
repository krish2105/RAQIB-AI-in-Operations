"""opinions: VLM second opinions (advisory).

Revision ID: 0003_opinions
Revises: 0002_ask_log
Create Date: 2026-09-06
"""

from __future__ import annotations

from sqlmodel import SQLModel

from alembic import op
from raqib_api import models  # noqa: F401

revision = "0003_opinions"
down_revision = "0002_ask_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    SQLModel.metadata.tables["opinions"].create(bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("alter table opinions enable row level security")


def downgrade() -> None:
    SQLModel.metadata.tables["opinions"].drop(op.get_bind(), checkfirst=True)
