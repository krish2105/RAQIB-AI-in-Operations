"""Sites are imported from the same YAML the edge box uses, so zones and floor plans match."""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlmodel import Session, select

from ..config import REPO_ROOT
from ..db import get_session
from ..models import Camera, Site, Zone
from ..schemas import SiteOut

router = APIRouter(prefix="/sites", tags=["sites"])

BUNDLED = {
    "raqib_demo_store": REPO_ROOT / "edge" / "sites" / "retail_demo.yaml",
    "greenlam_unit1": REPO_ROOT / "edge" / "sites" / "greenlam_unit1.yaml",
}


def import_site_yaml(session: Session, raw: dict) -> Site:
    site = session.get(Site, raw["name"])
    if site is None:
        site = Site(name=raw["name"], profile=raw["profile"])
        session.add(site)
    site.profile = raw["profile"]
    site.tills = int(raw.get("tills", 1))
    site.thresholds = dict(raw.get("thresholds", {}))
    site.floor = dict(raw.get("floor", {}))
    site.machines = list(raw.get("machines", []))
    for z in session.exec(select(Zone).where(Zone.site == site.name)).all():
        session.delete(z)
    for c in session.exec(select(Camera).where(Camera.site == site.name)).all():
        session.delete(c)
    for name, c in raw.get("cameras", {}).items():
        session.add(Camera(site=site.name, name=name, source=c.get("source", "file"), fps=float(c.get("fps", 25))))
    for z in raw.get("zones", []):
        session.add(Zone(site=site.name, name=z["name"], kind=z["kind"], camera=z["camera"],
                         polygon=[[float(x), float(y)] for x, y in z["polygon"]], meta=dict(z.get("meta", {}))))
    session.commit()
    session.refresh(site)
    return site


def ensure_bundled_sites(session: Session) -> None:
    for name, path in BUNDLED.items():
        if session.get(Site, name) is None and path.exists():
            import_site_yaml(session, yaml.safe_load(Path(path).read_text()))


def site_out(session: Session, site: Site) -> SiteOut:
    zones = session.exec(select(Zone).where(Zone.site == site.name)).all()
    cams = session.exec(select(Camera).where(Camera.site == site.name)).all()
    return SiteOut(
        name=site.name, profile=site.profile, tills=site.tills, thresholds=site.thresholds,
        floor=site.floor, machines=site.machines,
        zones=[{"name": z.name, "kind": z.kind, "camera": z.camera, "polygon": z.polygon, "meta": z.meta} for z in zones],
        cameras=[{"name": c.name, "source": c.source, "fps": c.fps} for c in cams],
    )


@router.get("", response_model=list[SiteOut])
def list_sites(session: Session = Depends(get_session)) -> list[SiteOut]:
    ensure_bundled_sites(session)
    return [site_out(session, s) for s in session.exec(select(Site)).all()]


@router.get("/{name}", response_model=SiteOut)
def get_site(name: str, session: Session = Depends(get_session)) -> SiteOut:
    ensure_bundled_sites(session)
    site = session.get(Site, name)
    if site is None:
        raise HTTPException(404, f"site {name!r} not found")
    return site_out(session, site)


@router.post("/import", response_model=SiteOut, status_code=201)
def import_site(body: str = Body(..., media_type="application/yaml"), session: Session = Depends(get_session)) -> SiteOut:
    raw = yaml.safe_load(body)
    if not isinstance(raw, dict) or "name" not in raw or raw.get("profile") not in ("retail", "factory"):
        raise HTTPException(422, "site YAML needs name and profile retail|factory")
    return site_out(session, import_site_yaml(session, raw))
