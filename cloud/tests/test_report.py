import re


def test_seed_then_kpis_forecast_workforce_report(client):
    r = client.post("/admin/seed", params={"site": "raqib_demo_store", "days": 21, "run_agent_last_hours": 3})
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
    r = client.post("/admin/seed", params={"site": "greenlam_unit1", "days": 15, "run_agent_last_hours": 24}).json()
    assert r["inserted"] > 500
    k = client.get("/kpis", params={"site": "greenlam_unit1"}).json()
    assert k["profile"] == "factory" and "compliance" in k and "downtime_min" in k
    rep = client.get("/report/weekly", params={"site": "greenlam_unit1", "lang": "en"}).json()
    assert len(rep["recommendations"]) == 3 and "MUSHRIF" in rep["markdown"]
    acts = client.get("/actions", params={"site": "greenlam_unit1"}).json()
    assert any(a["tool"] == "escalate" for a in acts)
    assert client.get("/report/weekly", params={"site": "nope"}).status_code == 404
