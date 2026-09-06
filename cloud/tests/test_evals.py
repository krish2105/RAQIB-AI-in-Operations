"""The Ask eval suite runs in CI mode (fake embeddings, no providers) and its retrieval gate holds."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from raqib_api.config import settings

CLOUD = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CLOUD / "evals" / "ask"))


def test_cases_file_has_30_trilingual_cases():
    cases = yaml.safe_load((CLOUD / "evals/ask/cases.yaml").read_text())["cases"]
    assert len(cases) == 30 and len({c["id"] for c in cases}) == 30
    assert {c["lang"] for c in cases} == {"en", "hi", "ar"} and all(c["expect"]["type"] in ("event", "doc", "kpi", "none") for c in cases)


def test_eval_suite_ci_mode_meets_retrieval_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "embed_model", "fake:64")
    monkeypatch.setattr(settings, "llm_provider_order", "groq")  # no key → deterministic paths only, no network
    monkeypatch.setattr(settings, "llm_provider", "groq")
    import run as ask_run

    out = tmp_path / "ask_eval.json"
    rc = ask_run.main(["--out", str(out), "--no-judge", "--gate"])
    data = json.loads(out.read_text())
    s = data["summary"]
    assert rc == 0, s
    assert s["cases"] == 30 and s["recall_at_5"] >= 0.8 and s["hallucinations"] == 0
    assert s["citation_coverage"] == 1.0 and s["language_match"] == 1.0
    assert s["paths"]["model"] == 0  # CI has no model: template + no_match only
