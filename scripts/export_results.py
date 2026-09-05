"""Pull every number the report, deck, and notebook cite from the running API into docs/results/.

  python3 scripts/export_results.py [--api http://localhost:8000]
Writes: kpis_retail.json, kpis_factory.json, forecast_retail.json, workforce_retail.json,
        report_retail_en.json, report_factory_en.json, toolcalls_retail.json, health.json
Rule: every figure in docs/ traces to a file here. No hand-typed numbers.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "docs" / "results"


def get(api: str, path: str):
    with urllib.request.urlopen(f"{api}{path}", timeout=120) as r:  # noqa: S310
        return json.load(r)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8000")
    a = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    jobs = {
        "health.json": "/health",
        "kpis_retail.json": "/kpis?site=raqib_demo_store",
        "kpis_factory.json": "/kpis?site=greenlam_unit1",
        "forecast_retail.json": "/forecast?site=raqib_demo_store&target=queue",
        "forecast_factory.json": "/forecast?site=greenlam_unit1&target=machine",
        "workforce_retail.json": "/workforce?site=raqib_demo_store",
        "report_retail_en.json": "/report/weekly?site=raqib_demo_store&lang=en",
        "report_factory_en.json": "/report/weekly?site=greenlam_unit1&lang=en",
        "toolcalls_retail.json": "/toolcalls/summary?site=raqib_demo_store",
        "toolcalls_factory.json": "/toolcalls/summary?site=greenlam_unit1",
    }
    for name, path in jobs.items():
        try:
            data = get(a.api, path)
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {name}: {exc}", file=sys.stderr)
            return 1
        (RESULTS / name).write_text(json.dumps(data, indent=2, default=str))
        print(f"wrote {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
