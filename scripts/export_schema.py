"""Emit the Postgres DDL for Supabase from the SQLModel metadata.

  cd cloud && uv run --no-sync python ../scripts/export_schema.py > supabase/schema.sql
  cd cloud && uv run --no-sync python ../scripts/export_schema.py --v2-only   # just the v2 tables + extras

The v2 extras (pgvector extension, HNSW index, tsvector column, RLS) mirror alembic/versions/0001_v2_tables.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cloud"))

from sqlalchemy import create_mock_engine  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from raqib_api import models  # noqa: E402  (registers tables)

v2_only = "--v2-only" in sys.argv
out: list[str] = ["-- RAQIB schema, generated from cloud/raqib_api/models.py. Apply in the Supabase SQL editor.",
                  "create extension if not exists vector;", ""]


def dump(sql, *multiparams, **params):
    out.append(str(sql.compile(dialect=postgresql.dialect())).strip() + ";\n")


engine = create_mock_engine("postgresql+psycopg://", dump)
tables = [SQLModel.metadata.tables[n] for n in models.V2_TABLES] if v2_only else None
SQLModel.metadata.create_all(engine, tables=tables, checkfirst=False)

out += [
    "-- v2 extras: ANN index, full-text column, row level security (API role bypasses RLS)",
    "create index if not exists ix_chunks_embedding_hnsw on chunks using hnsw (embedding vector_cosine_ops);",
    "alter table chunks add column if not exists tsv tsvector generated always as (to_tsvector('simple', coalesce(text, ''))) stored;",
    "create index if not exists ix_chunks_tsv on chunks using gin (tsv);",
]
all_tables = ("sites", "cameras", "zones", "events", "clips", "actions", "tool_calls", "forecasts") + tuple(models.V2_TABLES)
out += [f"alter table {t} enable row level security;" for t in all_tables]
print("\n".join(out))
