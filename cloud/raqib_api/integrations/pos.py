"""POS import: CSV today, Odoo and Shopify behind the same adapter interface later.

CSV columns (exact): ts, till, txn_id, items, amount. Rows are validated, invalid rows reported with their line,
and deduplicated on (site, txn_id) so importing the same file twice inserts nothing new.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlmodel import Session, select

from ..models import PosTransaction

COLUMNS = ("ts", "till", "txn_id", "items", "amount")


@dataclass(frozen=True)
class PosRow:
    ts: datetime
    till: int
    txn_id: str
    items: int
    amount: float


@dataclass
class ImportResult:
    site: str
    source: str
    inserted: int = 0
    duplicates: int = 0
    invalid: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"site": self.site, "source": self.source, "inserted": self.inserted, "duplicates": self.duplicates, "invalid": self.invalid,
                "errors": self.errors[:20]}


class PosAdapter(Protocol):
    name: str

    def fetch(self, since: datetime | None = None) -> list[PosRow]: ...


class NotConfigured(RuntimeError):
    pass


def parse_csv(text: str) -> tuple[list[PosRow], list[str]]:
    reader = csv.DictReader(io.StringIO(text))
    cols = tuple(c.strip() for c in (reader.fieldnames or []))
    if set(cols) != set(COLUMNS):
        return [], [f"columns must be exactly {', '.join(COLUMNS)}; got {', '.join(cols) or 'none'}"]
    rows: list[PosRow] = []
    errors: list[str] = []
    seen: set[str] = set()
    for i, r in enumerate(reader, start=2):
        try:
            ts = datetime.fromisoformat(r["ts"].strip().replace("Z", "+00:00"))
            ts = ts if ts.tzinfo else ts.replace(tzinfo=UTC)
            till = int(r["till"])
            items = int(r["items"] or 0)
            amount = float(r["amount"] or 0)
            txn = r["txn_id"].strip()
            if not txn or till < 1 or items < 0 or amount < 0:
                raise ValueError("txn_id empty, till < 1, or negative items/amount")
            if txn in seen:
                raise ValueError(f"duplicate txn_id {txn} inside the file")
            seen.add(txn)
            rows.append(PosRow(ts=ts, till=till, txn_id=txn, items=items, amount=amount))
        except (KeyError, ValueError) as exc:
            errors.append(f"line {i}: {exc}")
    return rows, errors


class CsvAdapter:
    name = "csv"

    def __init__(self, text: str) -> None:
        self.rows, self.errors = parse_csv(text)

    def fetch(self, since: datetime | None = None) -> list[PosRow]:
        return [r for r in self.rows if since is None or r.ts >= since]


class OdooAdapter:
    """Stub: the same interface, wired to Odoo's POS order endpoint when a pilot provides credentials."""

    name = "odoo"

    def __init__(self, url: str | None = None, api_key: str | None = None) -> None:
        self.url, self.api_key = url, api_key

    def fetch(self, since: datetime | None = None) -> list[PosRow]:
        raise NotConfigured("Odoo adapter is a stub: set ODOO_URL and ODOO_API_KEY and implement fetch() against /api/pos.order")


class ShopifyAdapter:
    name = "shopify"

    def __init__(self, shop: str | None = None, token: str | None = None) -> None:
        self.shop, self.token = shop, token

    def fetch(self, since: datetime | None = None) -> list[PosRow]:
        raise NotConfigured("Shopify adapter is a stub: set SHOPIFY_SHOP and SHOPIFY_TOKEN and implement fetch() against /admin/api/orders")


def import_rows(site: str, rows: list[PosRow], session: Session, source: str = "csv", errors: list[str] | None = None) -> ImportResult:
    res = ImportResult(site=site, source=source, errors=list(errors or []), invalid=len(errors or []))
    existing = set(session.exec(select(PosTransaction.txn_id).where(PosTransaction.site == site, PosTransaction.txn_id.in_([r.txn_id for r in rows]))).all()) if rows else set()
    for r in rows:
        if r.txn_id in existing:
            res.duplicates += 1
            continue
        session.add(PosTransaction(site=site, txn_id=r.txn_id, ts=r.ts, till=r.till, items=r.items, amount=r.amount, source=source))
        res.inserted += 1
    session.commit()
    return res


def transactions(site: str, session: Session, since: datetime | None = None, until: datetime | None = None) -> list[PosTransaction]:
    q = select(PosTransaction).where(PosTransaction.site == site)
    if since is not None:
        q = q.where(PosTransaction.ts >= since.replace(tzinfo=None))
    if until is not None:
        q = q.where(PosTransaction.ts < until.replace(tzinfo=None))
    return session.exec(q.order_by(PosTransaction.ts)).all()


def sample_csv(events: list[Any], seed: int = 7) -> str:
    """A labelled sample POS export derived from checkout_served events: one transaction per completion,
    basket size and amount drawn deterministically. Lets the demo import 'real-shaped' POS data."""
    import random

    rnd = random.Random(seed)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(COLUMNS)
    n = 0
    for e in events:
        if e.kind != "checkout_served":
            continue
        n += 1
        items = max(1, int(rnd.gauss(9, 4)))
        w.writerow([e.ts.isoformat(), int(e.payload.get("till", 1) or 1), f"SIM-{n:06d}", items, round(items * rnd.uniform(4.5, 14.0), 2)])
    return out.getvalue()
