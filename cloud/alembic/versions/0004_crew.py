"""crew: agent attribution on actions, crew_flags (kill switch), memory_snapshots.

Revision ID: 0004_crew
Revises: 0003_opinions
Create Date: 2026-09-06
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlmodel import SQLModel

from alembic import op
from raqib_api import models  # noqa: F401

revision = "0004_crew"
down_revision = "0003_opinions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    cols = {c["name"] for c in sa.inspect(bind).get_columns("actions")}
    with op.batch_alter_table("actions") as b:
        if "agent" not in cols:
            b.add_column(sa.Column("agent", sa.String(), nullable=True))
        if "run_id" not in cols:
            b.add_column(sa.Column("run_id", sa.String(), nullable=True))
    op.create_index("ix_actions_agent", "actions", ["agent"], if_not_exists=True)
    op.create_index("ix_actions_run_id", "actions", ["run_id"], if_not_exists=True)
    for t in ("crew_flags", "memory_snapshots"):
        SQLModel.metadata.tables[t].create(bind, checkfirst=True)
        if bind.dialect.name == "postgresql":
            op.execute(f"alter table {t} enable row level security")


def downgrade() -> None:
    bind = op.get_bind()
    for t in ("memory_snapshots", "crew_flags"):
        SQLModel.metadata.tables[t].drop(bind, checkfirst=True)
    op.drop_index("ix_actions_run_id", "actions", if_exists=True)
    op.drop_index("ix_actions_agent", "actions", if_exists=True)
    with op.batch_alter_table("actions") as b:
        b.drop_column("run_id")
        b.drop_column("agent")
