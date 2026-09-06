"""Planogram diff on synthetic shelf faces: a removed facing is missing, a swapped colour is misplaced, a full shelf is compliant."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from raqib_edge.planogram import Planogram, cell_empty, diff, load_planogram

FIX = Path(__file__).parent / "fixtures" / "shelf"
POLY = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
COLOURS = [(30, 60, 200), (200, 60, 30), (60, 200, 60), (200, 200, 30), (200, 30, 200), (30, 200, 200), (120, 120, 200), (90, 60, 30)]


def shelf_face(cols=4, rows=2, w=320, h=160, blank: set[tuple[int, int]] = frozenset(), swap: dict[tuple[int, int], tuple[int, int, int]] | None = None) -> np.ndarray:
    """Textured coloured blocks per cell (a stocked facing); a blank cell is flat grey (an empty facing)."""
    img = np.full((h, w, 3), 170, np.uint8)
    cw, ch = w // cols, h // rows
    rnd = np.random.RandomState(1)
    for r in range(rows):
        for c in range(cols):
            if (c, r) in blank:
                continue
            colour = (swap or {}).get((c, r), COLOURS[(r * cols + c) % len(COLOURS)])
            cell = img[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]
            cell[:] = colour
            noise = rnd.randint(-25, 25, cell.shape).astype(np.int16)  # product texture
            cell[:] = np.clip(cell.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            for k in range(6, cw, 12):  # pack edges
                cv2.line(cell, (k, 0), (k, ch), (255, 255, 255), 1)
    return img


def test_load_planogram_json_and_csv(tmp_path):
    pg = load_planogram(FIX / "a1.json")
    assert pg.shelf_id == "A1" and (pg.cols, pg.rows) == (4, 2) and pg.expected == 9 and pg.cell_of("A1-nuts") == (2, 1)
    csv = "shelf_id,sku,col,row,facings,price\nB3,milk,0,0,2,5.5\nB3,yogurt,1,0,1,3.25\n"
    (tmp_path / "b3.csv").write_text(csv)
    pg2 = load_planogram(tmp_path / "b3.csv")
    assert pg2.shelf_id == "B3" and pg2.cols == 2 and pg2.expected == 3 and pg2.facings[0].price == 5.5


def test_full_shelf_is_compliant_and_cell_empty_detects_flat_cells():
    pg = load_planogram(FIX / "a1.json")
    full = shelf_face()
    d = diff(full, POLY, pg)
    assert d.missing == [] and d.misplaced == [] and d.present == pg.expected and d.compliance == 1.0
    assert cell_empty(np.full((40, 80, 3), 170, np.uint8)) and not cell_empty(full[0:80, 0:80])


def test_removed_facing_is_reported_missing():
    pg = load_planogram(FIX / "a1.json")
    d = diff(shelf_face(blank={(2, 0)}), POLY, pg)
    assert [m["sku"] for m in d.missing] == ["A1-mints"] and d.present == pg.expected - 1 and d.drift == 1
    assert d.as_dict()["compliance"] == round(1 - 1 / 9, 3)


def test_swapped_product_is_misplaced_against_the_reference_photo():
    pg = load_planogram(FIX / "a1.json")
    pg.reference = shelf_face()
    d = diff(shelf_face(swap={(3, 1): (30, 60, 200)}), POLY, pg)  # cookies cell now shows the chocolate colour
    assert [m["sku"] for m in d.misplaced] == ["A1-cookies"] and d.missing == [] and d.drift == 1
    d2 = diff(shelf_face(), POLY, Planogram("A1", 4, 2, pg.facings, reference=shelf_face()))
    assert d2.drift == 0  # same photo, no drift
