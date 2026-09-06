"""POS: CSV import, summary (μ from POS vs video), transactions, a labelled sample export."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlmodel import Session, func, select

from ..db import get_session
from ..integrations.pos import CsvAdapter, import_rows, sample_csv, transactions
from ..models import Event, PosTransaction, Site
from ..ops_theory import slot_rates
from ..tz import ensure_utc

router = APIRouter(prefix="/pos", tags=["pos"])


@router.post("/import", status_code=201)
async def import_csv(site: str = Form(...), file: UploadFile = File(...), session: Session = Depends(get_session)) -> dict:
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(415, "upload a .csv with columns ts, till, txn_id, items, amount")
    text = (await file.read()).decode("utf-8", errors="replace")
    if len(text) > 20 * 1024 * 1024:
        raise HTTPException(413, "file larger than 20 MB")
    ad = CsvAdapter(text)
    if not ad.rows and ad.errors:
        raise HTTPException(422, ad.errors[0])
    return import_rows(site, ad.fetch(), session, source="csv", errors=ad.errors).as_dict()


@router.get("/summary")
def summary(site: str = Query(...), window_h: float = Query(24 * 7, gt=0), session: Session = Depends(get_session)) -> dict:
    s = session.get(Site, site)
    tills = s.tills if s else 3
    now = datetime.now(UTC)
    since = now - timedelta(hours=window_h)
    total = session.exec(select(func.count()).select_from(PosTransaction).where(PosTransaction.site == site)).one()
    first = session.exec(select(func.min(PosTransaction.ts)).where(PosTransaction.site == site)).one()
    last = session.exec(select(func.max(PosTransaction.ts)).where(PosTransaction.site == site)).one()
    pos = transactions(site, session, since=since)
    events = ensure_utc(session.exec(select(Event).where(Event.site == site, Event.ts >= since.replace(tzinfo=None), Event.kind.in_(["footfall_tick", "checkout_served"]))).all())
    with_pos = slot_rates(events, tills_open=tills, pos=[type("T", (), {"ts": t.ts.replace(tzinfo=UTC) if t.ts.tzinfo is None else t.ts, "till": t.till})() for t in pos])
    video = slot_rates(events, tills_open=tills)
    mu_pos = [x.mu_per_h for x in with_pos if x.mu_source == "pos"]
    mu_vid = [x.mu_per_h for x in video if x.served > 0]
    return {"site": site, "transactions": int(total), "first": first, "last": last, "window_h": window_h, "in_window": len(pos),
            "tills_seen": sorted({t.till for t in pos}), "mu_pos_per_h": round(sum(mu_pos) / len(mu_pos), 2) if mu_pos else None,
            "mu_video_per_h": round(sum(mu_vid) / len(mu_vid), 2) if mu_vid else None, "slots_with_pos": len(mu_pos), "slots": len(video),
            "mu_source": "pos" if mu_pos else "estimated_from_video",
            "adapters": {"csv": "ready", "odoo": "stub (ODOO_URL, ODOO_API_KEY)", "shopify": "stub (SHOPIFY_SHOP, SHOPIFY_TOKEN)"}}


@router.get("/transactions")
def list_transactions(site: str = Query(...), limit: int = Query(100, ge=1, le=2000), session: Session = Depends(get_session)) -> list[dict]:
    rows = session.exec(select(PosTransaction).where(PosTransaction.site == site).order_by(PosTransaction.ts.desc()).limit(limit)).all()
    return [{"txn_id": t.txn_id, "ts": t.ts, "till": t.till, "items": t.items, "amount": t.amount, "source": t.source} for t in rows]


@router.get("/sample")
def sample(site: str = Query(...), days: float = Query(7, gt=0, le=60), session: Session = Depends(get_session)) -> PlainTextResponse:
    """A labelled sample export derived from the site's checkout events (simulated history stays labelled SIM-)."""
    since = datetime.now(UTC) - timedelta(days=days)
    events = ensure_utc(session.exec(select(Event).where(Event.site == site, Event.kind == "checkout_served", Event.ts >= since.replace(tzinfo=None)).order_by(Event.ts)).all())
    return PlainTextResponse(sample_csv(events), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="pos_sample_{site}.csv"'})
