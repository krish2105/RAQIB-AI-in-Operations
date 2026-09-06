import re
from datetime import UTC, datetime, timedelta


def test_seed_then_kpis_forecast_workforce_report(client):
    # A 24 h window always spans some of the store's 08:00-23:00 open hours, so at least one
    # queue/shelf event — and therefore one agent action — is guaranteed regardless of the
    # real-world hour this suite happens to run in (the simulator's footfall rate is a function
    # of actual UTC hour-of-day and weekday, so a narrower window is not reliably non-empty).
    r = client.post("/admin/seed", params={"site": "raqib_demo_store", "days": 21, "run_agent_last_hours": 24})
    assert r.status_code == 200
    body = r.json()
    assert body["inserted"] > 2000 and body["simulated"] is True
    assert body["actions_created"] >= 1

    k = client.get("/kpis", params={"site": "raqib_demo_store"}).json()
    assert k["profile"] == "retail" and k["footfall"] > 0 and k["queue_model"]
    assert k["simulated_share"] == 1.0
    assert k["service_level"] is not None and k["osa_store"] is not None

    f = client.get("/forecast", params={"site": "raqib_demo_store", "target": "queue"}).json()
    assert f["sufficient"] is True and f["mae"] is not None and len(f["forecast"]) == 24
    assert f["improvement_pct"] > 0, f

    w = client.get("/workforce", params={"site": "raqib_demo_store"}).json()
    assert w["sufficient"] and len(w["tills"]) == len(w["slots"]) and w["savings_hours"] >= 0

    for lang in ("en", "hi", "ar"):
        rep = client.get("/report/weekly", params={"site": "raqib_demo_store", "lang": lang}).json()
        assert len(rep["recommendations"]) == 3
        for rec in rep["recommendations"]:
            assert rec["title"] and rec["evidence"] and rec["expected_reduction"]
        md = rep["markdown"]
        assert md.count("## ") == 7, md[:400]
        assert "TODO" not in md and "[insert" not in md
        assert not re.search(r"\bNone\b", md), "unrendered None in report"
    md = client.get("/report/weekly", params={"site": "raqib_demo_store", "format": "md"})
    assert md.headers["content-type"].startswith("text/markdown")
    assert rep["before_after"]["reduction_pct"] >= 0


def test_factory_seed_and_report(client):
    run_agent_last_hours = 24
    before = datetime.now(UTC)
    r = client.post("/admin/seed", params={"site": "greenlam_unit1", "days": 15, "run_agent_last_hours": run_agent_last_hours}).json()
    assert r["inserted"] > 500
    k = client.get("/kpis", params={"site": "greenlam_unit1"}).json()
    assert k["profile"] == "factory" and "compliance" in k and "downtime_min" in k
    rep = client.get("/report/weekly", params={"site": "greenlam_unit1", "lang": "en"}).json()
    assert len(rep["recommendations"]) == 3 and "MUSHRIF" in rep["markdown"]
    acts = client.get("/actions", params={"site": "greenlam_unit1"}).json()
    assert r["actions_created"] == len(acts) > 0

    # The seed's own cutoff is anchored to its own `datetime.now()`, taken mid-request; ours
    # is taken just before the call, so widen the window by one hour to avoid an off-by-a-few-
    # seconds boundary miss. Whether escalate actually fired depends on the simulator's RNG
    # landing a severity-3 event inside that window — never hardcode "at least one" here, since
    # that count shifts with the wall-clock hour the suite happens to run in (the simulator's
    # footfall rate is a function of real hour-of-day and weekday). Instead assert the agent's
    # behaviour is *consistent* with what actually landed in the window.
    cutoff = before - timedelta(hours=run_agent_last_hours + 1)
    severity3 = client.get("/events", params={"site": "greenlam_unit1", "since": cutoff.isoformat(), "min_severity": 3, "limit": 5000}).json()
    escalate_actions = [a for a in acts if a["tool"] == "escalate"]
    if severity3:
        assert escalate_actions, f"{len(severity3)} severity-3 events in the window but no escalate action was recorded"
        assert all(a["autonomous"] and a["status"] == "executed" for a in escalate_actions)
    else:
        assert not escalate_actions

    assert client.get("/report/weekly", params={"site": "nope"}).status_code == 404


def test_report_narrative_is_empty_without_index_and_cited_with_index(client, monkeypatch):
    """Ask-generated sections appear only once records are indexed; each carries citations."""
    from raqib_api.config import settings

    monkeypatch.setattr(settings, "embed_model", "fake:64")
    monkeypatch.setattr(settings, "llm_provider", "groq")
    monkeypatch.setattr(settings, "llm_provider_order", "groq")
    client.post("/admin/seed", params={"site": "raqib_demo_store", "days": 8, "run_agent_last_hours": 0})
    r = client.get("/report/weekly", params={"site": "raqib_demo_store", "lang": "en"}).json()
    assert r["narrative"] == []
    ix = client.post("/admin/index", params={"site": "raqib_demo_store", "days": 8}).json()
    assert ix["chunks"] > 0 and ix["embedded"] == ix["chunks"]
    r = client.get("/report/weekly", params={"site": "raqib_demo_store", "lang": "hi"}).json()
    assert len(r["narrative"]) == 3 and all(n["citations"] for n in r["narrative"]) and r["narrative"][0]["title"] == "कतारें"
    assert "रिकॉर्ड क्या कहते हैं" in r["markdown"] and "[c:" in r["markdown"]
    assert client.post("/admin/index", params={"site": "nope"}).status_code == 404
