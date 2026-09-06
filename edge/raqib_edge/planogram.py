"""Planogram diff: expected facings per shelf vs what the shelf ROI shows.

A planogram is a JSON/CSV grid of facings for one shelf ROI (normalised cells inside the shelf polygon's
bounding box), optionally with a reference photo. The diff is deterministic image arithmetic:
  missing   = an expected facing whose cell reads as empty (edge density and colour spread both low)
  misplaced = a cell whose mean colour is far from the reference photo's cell (ΔE in Lab above a threshold)
It never identifies people; it only looks at shelf pixels inside shelf zones.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class Facing:
    sku: str
    col: int
    row: int
    facings: int = 1
    price: float | None = None


@dataclass
class Planogram:
    shelf_id: str
    cols: int
    rows: int
    facings: list[Facing]
    reference: np.ndarray | None = None  # BGR reference photo of the shelf ROI

    @property
    def expected(self) -> int:
        return sum(f.facings for f in self.facings)

    def cell_of(self, sku: str) -> tuple[int, int] | None:
        for f in self.facings:
            if f.sku == sku:
                return f.col, f.row
        return None


@dataclass
class PlanogramDiff:
    shelf_id: str
    expected: int
    present: int
    missing: list[dict[str, Any]] = field(default_factory=list)
    misplaced: list[dict[str, Any]] = field(default_factory=list)

    @property
    def drift(self) -> int:
        return len(self.missing) + len(self.misplaced)

    @property
    def compliance(self) -> float:
        return 1.0 - self.drift / self.expected if self.expected else 1.0

    def as_dict(self) -> dict[str, Any]:
        return {"shelf_id": self.shelf_id, "expected": self.expected, "present": self.present, "missing": self.missing,
                "misplaced": self.misplaced, "drift": self.drift, "compliance": round(self.compliance, 3)}


def load_planogram(path: str | Path, reference: str | Path | None = None) -> Planogram:
    p = Path(path)
    if p.suffix.lower() == ".json":
        d = json.loads(p.read_text())
        facings = [Facing(str(f["sku"]), int(f["col"]), int(f["row"]), int(f.get("facings", 1)), f.get("price")) for f in d["facings"]]
        pg = Planogram(str(d["shelf_id"]), int(d["cols"]), int(d["rows"]), facings)
    else:  # csv: shelf_id,sku,col,row,facings,price
        rows = list(csv.DictReader(io.StringIO(p.read_text())))
        if not rows:
            raise ValueError(f"empty planogram {p}")
        facings = [Facing(r["sku"], int(r["col"]), int(r["row"]), int(r.get("facings") or 1), float(r["price"]) if r.get("price") else None) for r in rows]
        pg = Planogram(rows[0]["shelf_id"], max(f.col for f in facings) + 1, max(f.row for f in facings) + 1, facings)
    if reference and Path(reference).exists():
        pg.reference = cv2.imread(str(reference))
    return pg


def _roi(frame: np.ndarray, polygon_norm: list[tuple[float, float]]) -> np.ndarray | None:
    h, w = frame.shape[:2]
    xs = [int(x * w) for x, _ in polygon_norm]
    ys = [int(y * h) for _, y in polygon_norm]
    x1, x2, y1, y2 = max(0, min(xs)), min(w, max(xs)), max(0, min(ys)), min(h, max(ys))
    if x2 - x1 < 12 or y2 - y1 < 12:
        return None
    return frame[y1:y2, x1:x2]


def _cell(roi: np.ndarray, cols: int, rows: int, col: int, row: int) -> np.ndarray:
    h, w = roi.shape[:2]
    cw, ch = w // cols, h // rows
    return roi[row * ch:(row + 1) * ch, col * cw:(col + 1) * cw]


def cell_empty(cell: np.ndarray, edge_thr: float = 0.04, std_thr: float = 18.0) -> bool:
    if cell.size == 0:
        return True
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 140)
    return float((edges > 0).mean()) < edge_thr and float(cell.reshape(-1, 3).std(axis=0).mean()) < std_thr


def _lab_mean(cell: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(cell, cv2.COLOR_BGR2LAB).reshape(-1, 3).mean(axis=0)


def diff(frame: np.ndarray, polygon_norm: list[tuple[float, float]], pg: Planogram, delta_e_thr: float = 25.0) -> PlanogramDiff:
    roi = _roi(frame, polygon_norm)
    out = PlanogramDiff(pg.shelf_id, pg.expected, 0)
    if roi is None:
        return out
    ref = cv2.resize(pg.reference, (roi.shape[1], roi.shape[0])) if pg.reference is not None else None
    for f in pg.facings:
        cell = _cell(roi, pg.cols, pg.rows, f.col, f.row)
        if cell_empty(cell):
            out.missing.append({"sku": f.sku, "col": f.col, "row": f.row, "facings": f.facings})
            continue
        if ref is not None:
            d = float(np.linalg.norm(_lab_mean(cell) - _lab_mean(_cell(ref, pg.cols, pg.rows, f.col, f.row))))
            if d > delta_e_thr:
                out.misplaced.append({"sku": f.sku, "col": f.col, "row": f.row, "delta_e": round(d, 1)})
                continue
        out.present += f.facings
    return out
