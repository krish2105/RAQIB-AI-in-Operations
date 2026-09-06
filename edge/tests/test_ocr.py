"""Price-tag OCR: parse_price is deterministic; an installed engine reads a printed tag within tolerance."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from raqib_edge.ocr import NullOcr, OcrText, make_ocr, parse_price, read_price_tags


def test_parse_price_handles_currency_forms():
    assert parse_price("AED 5.50") == 5.5 and parse_price("5,50 Dhs") == 5.5 and parse_price("AED: 5.50") == 5.5
    assert parse_price("د.إ 12") == 12.0 and parse_price("Price 3.25 AED") == 3.25 and parse_price("no digits here") is None


def _tag(text: str) -> np.ndarray:
    img = np.full((120, 360, 3), 255, np.uint8)
    cv2.putText(img, text, (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 4)
    return img


def test_read_price_tags_with_a_fake_engine_and_null_engine():
    class Fake:
        name = "fake"

        def read(self, image):
            return [OcrText("AED 5.50", 0.9)]

    frame = np.full((240, 720, 3), 255, np.uint8)
    reads = read_price_tags(frame, [{"tag": "A1-wafer", "polygon": [[0, 0], [0.5, 0], [0.5, 0.5], [0, 0.5]]}, {"tag": "tiny", "polygon": [[0, 0], [0.001, 0], [0.001, 0.001], [0, 0.001]]}], Fake())
    assert reads[0].price == 5.5 and reads[0].conf == 0.9 and reads[0].engine == "fake"
    assert reads[1].price is None and reads[1].text == ""
    assert read_price_tags(frame, [{"tag": "x", "polygon": [[0, 0], [1, 0], [1, 1], [0, 1]]}], NullOcr())[0].price is None


def test_installed_engine_reads_the_printed_price_within_tolerance():
    eng = make_ocr()
    if eng.name == "none":
        pytest.skip("no OCR engine installed (uv sync --extra ocr)")
    frame = np.full((240, 720, 3), 255, np.uint8)
    frame[60:180, 180:540] = _tag("AED 5.50")
    reads = read_price_tags(frame, [{"tag": "A1-wafer", "polygon": [[0.25, 0.25], [0.75, 0.25], [0.75, 0.75], [0.25, 0.75]]}], eng)
    assert reads[0].price is not None and abs(reads[0].price - 5.5) <= 0.05, reads
    assert reads[0].engine in ("apple_vision", "rapidocr") and reads[0].conf > 0.5
