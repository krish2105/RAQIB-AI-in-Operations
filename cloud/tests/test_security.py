"""Task 43: security headers, SSRF guard, evidence rule, and the security router."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from raqib_api.routers.documents import guard_url


def test_every_response_carries_defensive_headers(client):
    r = client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/x", "http://localhost/x", "http://169.254.169.254/latest/meta-data", "http://10.0.0.5/a", "http://[::1]/", "ftp://example.com/a", "file:///etc/passwd", "http://user:pw@example.com/"])
def test_ssrf_guard_refuses_private_and_odd_urls(url):
    with pytest.raises(HTTPException) as exc:
        guard_url(url)
    assert exc.value.status_code == 422


def test_ssrf_guard_allows_public(monkeypatch):
    import socket

    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: [(2, 1, 6, "", ("93.184.216.34", 0))])
    assert guard_url("https://example.com/doc.md") == "https://example.com/doc.md"


def test_documents_url_route_blocks_metadata_endpoint(client):
    r = client.post("/documents/url", json={"site": "raqib_demo_store", "kind": "sop", "url": "http://169.254.169.254/latest/meta-data"})
    assert r.status_code == 422 and "non-public" in r.json()["detail"]


def test_security_router_serves_scorecard_and_guard_log(client, tmp_path, monkeypatch):
    from raqib_api.routers import security as sec

    monkeypatch.setattr(sec, "RESULTS", tmp_path / "missing.json")
    r = client.get("/security/scorecard")
    assert r.status_code == 200 and r.json()["total"] == 0
    (tmp_path / "r.json").write_text('{"date": "2026-09-06", "passed": 10, "failed": 0, "total": 10, "results": [{"asi": "ASI01", "risk": "Goal hijack", "test": "t", "passed": true, "evidence": {"seconds": 0.1, "proposals": 0}}]}')
    monkeypatch.setattr(sec, "RESULTS", tmp_path / "r.json")
    assert client.get("/security/scorecard").json()["passed"] == 10
    runs = client.get("/security/redteam").json()["runs"]
    assert runs[0]["asi"] == "ASI01" and runs[0]["evidence"] == {"proposals": 0}
    g = client.get("/security/memory-guard", params={"site": "raqib_demo_store"})
    assert g.status_code == 200 and set(g.json()) >= {"quarantined", "quarantine_actions", "snapshots"}
    assert client.get("/security/audit", params={"site": "raqib_demo_store"}).json()["flagged"] == []
