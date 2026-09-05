"""Train a small stocked/empty shelf-cell classifier from labelled crops.

Data layout (manual labelling of site footage, or MVTec-style folders):
  edge/data/datasets/shelf/{stocked,empty}/*.jpg
Model: HOG + colour-histogram features -> scikit-learn GradientBoostingClassifier.
Writes edge/data/weights/shelf_gbc.joblib and docs/results/shelf_train.json.
The heuristic in raqib_edge/shelf.py stays the default until this file exists.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "edge" / "data" / "datasets" / "shelf"
OUT = REPO / "edge" / "data" / "weights" / "shelf_gbc.joblib"
RESULTS = REPO / "docs" / "results"


def features(img: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(cv2.resize(img, (64, 64)), cv2.COLOR_BGR2GRAY)
    hog = cv2.HOGDescriptor((64, 64), (16, 16), (8, 8), (8, 8), 9).compute(g).ravel()
    hsv = cv2.cvtColor(cv2.resize(img, (64, 64)), cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [8, 4], [0, 180, 0, 256]).ravel()
    hist = hist / (hist.sum() + 1e-6)
    edges = cv2.Canny(g, 60, 140)
    return np.concatenate([hog, hist, [np.count_nonzero(edges) / edges.size, g.std()]])


def main() -> int:
    if not DATA.exists():
        print(f"MISSING: labelled shelf crops at {DATA}/{{stocked,empty}}/. Label ~200 crops from site footage.", file=sys.stderr)
        return 2
    import joblib
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score

    X, y = [], []
    for label, cls in (("stocked", 0), ("empty", 1)):
        for p in (DATA / label).glob("*.jpg"):
            im = cv2.imread(str(p))
            if im is not None:
                X.append(features(im))
                y.append(cls)
    X, y = np.array(X), np.array(y)
    clf = GradientBoostingClassifier(random_state=0)
    acc = cross_val_score(clf, X, y, cv=5).mean()
    clf.fit(X, y)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, OUT)
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "shelf_train.json").write_text(json.dumps({"n": int(len(y)), "cv_accuracy": float(acc)}, indent=2))
    print(f"cv accuracy {acc:.3f} on {len(y)} crops -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
