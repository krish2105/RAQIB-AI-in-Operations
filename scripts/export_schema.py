"""Emit the Postgres DDL for Supabase from the SQLModel metadata.

  cd cloud && uv run --no-sync python ../scripts/export_schema.py > supabase/schema.sql
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cloud"))

from sqlalchemy import create_mock_engine  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import raqib_api.models  # noqa: E402,F401  (registers tables)

out: list[str] = ["-- RAQIB schema, generated from cloud/raqib_api/models.py. Apply in the Supabase SQL editor.", ""]


def dump(sql, *multiparams, **params):
    out.append(str(sql.compile(dialect=postgresql.dialect())).strip() + ";\n")


engine = create_mock_engine("postgresql+psycopg://", dump)
SQLModel.metadata.create_all(engine, checkfirst=False)
print("\n".join(out))
