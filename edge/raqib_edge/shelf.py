"""Shelf empty-ratio estimator.

A stocked shelf face is visually busy: many edges, high colour variance. An
empty stretch of shelf is flat and uniform. We tile the shelf polygon's bounding
box into cells and call a cell "empty" when both its edge density and its colour
standard deviation fall below thresholds. The ratio of empty cells is the
estimate. This is a heuristic proxy; the pilot replaces it with a trained
shelf model (edge/training/train_shelf.py) behind the same function signature.
"""

from __future__ import annotations

import cv2
import numpy as np


def shelf_empty_ratio(
    frame: np.ndarray,
    polygon_norm: list[tuple[float, float]],
    grid: tuple[int, int] = (6, 3),
    edge_thr: float = 0.04,
    std_thr: float = 18.0,
) -> float:
    h, w = frame.shape[:2]
    xs = [int(x * w) for x, _ in polygon_norm]
    ys = [int(y * h) for _, y in polygon_norm]
    x1, x2 = max(0, min(xs)), min(w, max(xs))
    y1, y2 = max(0, min(ys)), min(h, max(ys))
    if x2 - x1 < 12 or y2 - y1 < 12:
        return 0.0
    roi = frame[y1:y2, x1:x2]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 140)
    cols, rows = grid
    cw, ch = (x2 - x1) // cols, (y2 - y1) // rows
    if cw < 4 or ch < 4:
        return 0.0
    empty = 0
    total = 0
    for r in range(rows):
        for c in range(cols):
            cell_e = edges[r * ch : (r + 1) * ch, c * cw : (c + 1) * cw]
            cell_c = roi[r * ch : (r + 1) * ch, c * cw : (c + 1) * cw]
            edge_density = float(np.count_nonzero(cell_e)) / cell_e.size
            colour_std = float(cell_c.reshape(-1, 3).std(axis=0).mean())
            total += 1
            if edge_density < edge_thr and colour_std < std_thr:
                empty += 1
    return empty / total if total else 0.0
