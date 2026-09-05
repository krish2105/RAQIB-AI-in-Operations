"""Fine-tune YOLO26n on SH17 for helmet / vest / person.

Usage:  uv run python training/train_ppe.py --epochs 30 --imgsz 640
Requires edge/data/datasets/sh17 (see prepare_data.py). Writes weights to
edge/data/weights/ppe_yolo26n.pt and a metrics JSON to docs/results/ppe_train.json.
Licence note: the resulting weights inherit SH17's CC BY-NC-SA 4.0 (non-commercial).
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from prepare_data import SPECS, check

REPO = Path(__file__).resolve().parents[2]
WEIGHTS = REPO / "edge" / "data" / "weights"
RESULTS = REPO / "docs" / "results"

# SH17 class names in the order used by the Kaggle release.
SH17_CLASSES = [
    "person", "head", "face", "glasses", "face-mask-medical", "face-guard", "ear", "earmuffs",
    "hands", "gloves", "foot", "shoes", "safety-vest", "tools", "helmet", "medical-suit", "safety-suit",
]


def write_data_yaml(root: Path) -> Path:
    y = root / "sh17.yaml"
    y.write_text(
        f"path: {root}\ntrain: images/train\nval: images/val\n"
        f"names:\n" + "".join(f"  {i}: {n}\n" for i, n in enumerate(SH17_CLASSES))
    )
    return y


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--base", default=str(WEIGHTS / "yolo26n.pt"))
    args = ap.parse_args(argv)

    root = check(SPECS["sh17"])
    if root is None:
        print("SH17 not found; run training/prepare_data.py --dataset sh17", file=sys.stderr)
        return 2
    from ultralytics import YOLO

    from raqib_edge.detectors import pick_device

    model = YOLO(args.base)
    res = model.train(
        data=str(write_data_yaml(root)), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
        device=pick_device(), project=str(REPO / "runs"), name="ppe", exist_ok=True, verbose=False,
    )
    best = Path(res.save_dir) / "weights" / "best.pt"
    shutil.copy(best, WEIGHTS / "ppe_yolo26n.pt")
    metrics = model.val(data=str(root / "sh17.yaml"), device=pick_device(), verbose=False)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "ppe_train.json").write_text(json.dumps({
        "dataset": "SH17", "licence": "CC BY-NC-SA 4.0", "epochs": args.epochs,
        "map50": float(metrics.box.map50), "map50_95": float(metrics.box.map),
        "per_class_map50": {SH17_CLASSES[i]: float(v) for i, v in enumerate(metrics.box.maps)},
    }, indent=2))
    print("wrote", WEIGHTS / "ppe_yolo26n.pt", "and", RESULTS / "ppe_train.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
