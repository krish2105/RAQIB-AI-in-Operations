"""raqib-api: indexing and housekeeping commands that run on the Mac / edge box."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta

from sqlmodel import Session

from .db import engine, init_db


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="raqib-api")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ix = sub.add_parser("index", help="chunk, caption and embed events/KPIs since a time")
    ix.add_argument("--site", default="raqib_demo_store")
    ix.add_argument("--since", default="7d", help="ISO timestamp or Nd/Nh (default 7d)")
    ix.add_argument("--no-embed", action="store_true")
    ix.add_argument("--no-captions", action="store_true")
    doc = sub.add_parser("add-document", help="ingest a local .md/.txt/.csv/.pdf")
    doc.add_argument("path")
    doc.add_argument("--site", default="raqib_demo_store")
    doc.add_argument("--kind", default="sop")
    doc.add_argument("--title", default="")
    doc.add_argument("--lang", default="en")
    a = ap.parse_args(argv)
    init_db()
    with Session(engine) as s:
        if a.cmd == "index":
            from .models import Site
            from .rag.indexer import index_since

            site = s.get(Site, a.site)
            stats = index_since(a.site, _since(a.since), s, embed=not a.no_embed, captions=not a.no_captions, tills=site.tills if site else 3)
            print(json.dumps(stats.as_dict(), indent=2))
        elif a.cmd == "add-document":
            from pathlib import Path

            from .rag.indexer import ingest_document

            p = Path(a.path)
            d, n, created = ingest_document(a.site, a.title or p.stem, a.kind, p.name, p.read_bytes(), s, lang=a.lang)
            print(json.dumps({"id": d.id, "title": d.title, "chunks": n, "created": created}))
    return 0


def _since(v: str) -> datetime:
    if v.endswith("d"):
        return datetime.now(UTC) - timedelta(days=float(v[:-1]))
    if v.endswith("h"):
        return datetime.now(UTC) - timedelta(hours=float(v[:-1]))
    return datetime.fromisoformat(v)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
