from conftest import make_event


def test_batch_ingest_is_idempotent(client):
    evs = [make_event(i) for i in range(3)]
    r = client.post("/events/batch", json={"events": evs})
    assert r.status_code == 201
    assert r.json()["inserted"] == 3 and r.json()["duplicates"] == 0
    r2 = client.post("/events/batch", json={"events": evs})
    assert r2.json() == {"inserted": 0, "duplicates": 3, "actions_created": 0}
    assert len(client.get("/events", params={"site": "raqib_demo_store"}).json()) == 3


def test_filters_and_404(client):
    client.post("/events/batch", json={"events": [
        make_event(0), make_event(1, kind="queue_over", severity=2, payload={"count": 5}, rule="R10"),
    ]})
    sev2 = client.get("/events", params={"severity": 2}).json()
    assert len(sev2) == 1 and sev2[0]["kind"] == "queue_over"
    assert client.get("/events", params={"kind": "footfall_tick"}).json()[0]["rule_id"] == "R12"
    assert client.get("/events/01AAAAAAAAAAAAAAAAAAAAAAAA").status_code == 404


def test_validation_rejects_bad_kind_and_severity(client):
    bad = make_event(0)
    bad["kind"] = "alien"
    assert client.post("/events/batch", json={"events": [bad]}).status_code == 422
    bad = make_event(0)
    bad["severity"] = 7
    assert client.post("/events/batch", json={"events": [bad]}).status_code == 422


def test_clip_upload_and_download(client):
    ev = make_event(0, kind="queue_over", severity=2, payload={"count": 4}, rule="R10")
    client.post("/events/batch", json={"events": [ev]})
    r = client.put(f"/clips/{ev['id']}", files={"file": ("c.mp4", b"\x00\x00\x00\x18ftyp" + b"x" * 64, "video/mp4")})
    assert r.status_code == 201 and r.json()["bytes"] == 72
    got = client.get(f"/clips/{ev['id']}")
    assert got.status_code == 200 and got.headers["content-type"].startswith("video/mp4")
    assert client.get(f"/events/{ev['id']}").json()["has_clip"] is True
    assert client.get("/clips/01AAAAAAAAAAAAAAAAAAAAAAAA").status_code == 404


def test_health_and_sites(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["agent_backend"] == "dryrun"
    sites = client.get("/sites").json()
    names = {s["name"] for s in sites}
    assert {"raqib_demo_store", "greenlam_unit1"} <= names
    demo = client.get("/sites/raqib_demo_store").json()
    assert demo["profile"] == "retail" and demo["tills"] == 3 and len(demo["zones"]) >= 4
    assert client.get("/sites/nope").status_code == 404


def test_site_import_yaml(client):
    yaml_doc = "name: t1\nprofile: factory\ncameras: {c: {source: webcam, uri: 0}}\nzones: [{name: e, kind: exclusion, camera: c, polygon: [[0,0],[1,0],[1,1]]}]\n"
    r = client.post("/sites/import", content=yaml_doc, headers={"content-type": "application/yaml"})
    assert r.status_code == 201 and r.json()["zones"][0]["kind"] == "exclusion"
    assert client.post("/sites/import", content="name: x\nprofile: farm\n", headers={"content-type": "application/yaml"}).status_code == 422
