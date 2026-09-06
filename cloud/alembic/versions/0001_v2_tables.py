"""v2 tables: captions, documents, chunks (pgvector), memories, agent runs/messages, users, stores, drift, quotas.

Revision ID: 0001_v2
Revises: None
Create Date: 2026-09-06

The table definitions come from `raqib_api.models` so the ORM and the migration cannot drift.
Postgres additionally gets: the `vector` extension, an HNSW index on chunks.embedding, a
generated `tsv` column with a GIN index for BM25-style search, and RLS enabled on every
table (the API connects as a BYPASSRLS role; PostgREST roles get nothing).
"""

from __future__ import annotations

from sqlmodel import SQLModel

from alembic import op
from raqib_api import models

revision = "0001_v2"
down_revision = None
branch_labels = None
depends_on = None

PHASE_AD_TABLES = ("sites", "cameras", "zones", "events", "clips", "actions", "tool_calls", "forecasts")


def _tables():
    return [SQLModel.metadata.tables[n] for n in models.V2_TABLES]


def upgrade() -> None:
    bind = op.get_bind()
    pg = bind.dialect.name == "postgresql"
    if pg:
        op.execute("create extension if not exists vector")
    # v2 tables reference events/documents; make sure the Phase A–D baseline exists on a fresh DB.
    SQLModel.metadata.create_all(bind, tables=[SQLModel.metadata.tables[n] for n in PHASE_AD_TABLES], checkfirst=True)
    SQLModel.metadata.create_all(bind, tables=_tables(), checkfirst=True)
    if pg:
        op.execute("create index if not exists ix_chunks_embedding_hnsw on chunks using hnsw (embedding vector_cosine_ops)")
        op.execute("alter table chunks add column if not exists tsv tsvector generated always as (to_tsvector('simple', coalesce(text, ''))) stored")
        op.execute("create index if not exists ix_chunks_tsv on chunks using gin (tsv)")
        for t in PHASE_AD_TABLES + tuple(models.V2_TABLES):
            op.execute(f"alter table {t} enable row level security")


def downgrade() -> None:
    bind = op.get_bind()
    for t in reversed(_tables()):
        t.drop(bind, checkfirst=True)
