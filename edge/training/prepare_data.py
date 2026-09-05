"""Check for (never silently download) licensed training datasets and record them.

Usage:  uv run python training/prepare_data.py --dataset sh17
        uv run python training/prepare_data.py --dataset mvtec

Exit codes: 0 found and recorded, 2 missing (prints name, licence, URL).
Rule (CLAUDE.md): if a dataset is unreachable, fail loudly. No synthetic fallback.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATASETS_DIR = REPO / "edge" / "data" / "datasets"
LEDGER = REPO / "docs" / "datasets.md"


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    name: str
    licence: str
    url: str
    expect: tuple[str, ...]  # files/dirs that must exist under the dataset dir
    use: str


SPECS: dict[str, DatasetSpec] = {
    "sh17": DatasetSpec(
        key="sh17",
        name="SH17: human safety and PPE detection (Ahmad & Rahimi, 2024)",
        licence="CC BY-NC-SA 4.0",
        url="https://www.kaggle.com/datasets/mugheesahmad/sh17-dataset-for-ppe-detection",
        expect=("images", "labels"),
        use="PPE fine-tuning (factory profile)",
    ),
    "mvtec": DatasetSpec(
        key="mvtec",
        name="MVTec Anomaly Detection (MVTec-AD)",
        licence="CC BY-NC-SA 4.0",
        url="https://www.mvtec.com/company/research/datasets/mvtec-ad",
        expect=("bottle", "screw"),
        use="machine-state classifier proxy tests",
    ),
    "mot17": DatasetSpec(
        key="mot17",
        name="MOT17 multi-object tracking benchmark",
        licence="CC BY-NC-SA 3.0",
        url="https://motchallenge.net/data/MOT17/",
        expect=("train",),
        use="tracker evaluation (optional)",
    ),
}


def check(spec: DatasetSpec) -> Path | None:
    root = DATASETS_DIR / spec.key
    if root.exists() and all((root / e).exists() for e in spec.expect):
        return root
    return None


def record(spec: DatasetSpec, root: Path) -> None:
    n_files = sum(1 for _ in root.rglob("*") if _.is_file())
    line = (
        f"| {spec.name} (verified) | `edge/data/datasets/{spec.key}/` | {spec.url} | {spec.licence} "
        f"| {n_files} files | {datetime.now(UTC).date()} | {spec.use} |\n"
    )
    text = LEDGER.read_text()
    if "(verified)" in text and spec.key in text.split("(verified)")[0][-200:]:
        return
    marker = "\n## Licence implications"
    LEDGER.write_text(text.replace(marker, line + marker, 1) if marker in text else text + line)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True, choices=sorted(SPECS))
    args = ap.parse_args(argv)
    spec = SPECS[args.dataset]
    root = check(spec)
    if root is None:
        print(
            f"MISSING DATASET: {spec.name}\n"
            f"  licence : {spec.licence}\n"
            f"  download: {spec.url}\n"
            f"  place at: {DATASETS_DIR / spec.key}/  (expected entries: {', '.join(spec.expect)})\n"
            "This dataset requires a manual download (account/licence acceptance). "
            "No synthetic fallback is used.",
            file=sys.stderr,
        )
        return 2
    record(spec, root)
    print(f"OK {spec.key} at {root} ({spec.licence}); recorded in docs/datasets.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
