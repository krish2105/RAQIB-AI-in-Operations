from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlmodel import Session

from ..agent.weekly_agent import build_report_data, narrative_sections, recommend, render_markdown
from ..db import get_session
from .sites import ensure_bundled_sites

router = APIRouter(tags=["report"])


@router.get("/report/weekly")
def weekly(site: str, lang: str = Query("en", pattern="^(en|hi|ar)$"), format: str = Query("json", pattern="^(json|md)$"),
           session: Session = Depends(get_session)):
    ensure_bundled_sites(session)
    try:
        data = build_report_data(site, session)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    recs = recommend(data)
    data["narrative"] = narrative_sections(site, session, lang)  # Ask-generated sections, cited; [] when nothing is indexed
    if format == "md":
        return PlainTextResponse(render_markdown(data, recs, lang), media_type="text/markdown; charset=utf-8")
    return {**data, "lang": lang, "recommendations": recs, "markdown": render_markdown(data, recs, lang)}
