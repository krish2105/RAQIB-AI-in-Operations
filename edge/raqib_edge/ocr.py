"""Price-tag OCR behind an adapter: Apple Vision (pyobjc) on macOS, RapidOCR (ONNX) elsewhere.

Tags are read inside shelf ROIs only. The frame is already blurred (tags are not faces, the blur does not
touch them). A read is a price in AED; a mismatch against the price list is rule R14's input.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

log = logging.getLogger(__name__)

PRICE = re.compile(r"(?:(?:AED|Dhs?|د\.إ|درهم)\s*)?(\d{1,4}(?:[.,]\d{1,2})?)(?:\s*(?:AED|Dhs?|د\.إ|درهم))?", re.IGNORECASE)


@dataclass(frozen=True)
class OcrText:
    text: str
    conf: float
    box: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class PriceRead:
    tag: str
    text: str
    price: float | None
    conf: float
    engine: str


class OcrEngine(Protocol):
    name: str

    def read(self, image: np.ndarray) -> list[OcrText]: ...


def parse_price(text: str) -> float | None:
    """'AED 5.50' -> 5.5, '5,50 Dhs' -> 5.5, 'AED: 5.50' -> 5.5; None when no number."""
    m = PRICE.search(text.replace(":", " "))
    if not m:
        return None
    try:
        return round(float(m.group(1).replace(",", ".")), 2)
    except ValueError:
        return None


class VisionOcr:
    name = "apple_vision"

    def read(self, image: np.ndarray) -> list[OcrText]:
        import cv2
        import Quartz
        import Vision

        ok, buf = cv2.imencode(".png", image)
        data = Quartz.CFDataCreate(None, bytes(buf), len(buf))
        src = Quartz.CGImageSourceCreateWithData(data, None)
        cg = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
        req = Vision.VNRecognizeTextRequest.alloc().init()
        req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
        handler.performRequests_error_([req], None)
        out = []
        for o in req.results() or []:
            c = o.topCandidates_(1)[0]
            bb = o.boundingBox()
            out.append(OcrText(str(c.string()), float(o.confidence()), (bb.origin.x, 1 - bb.origin.y - bb.size.height, bb.size.width, bb.size.height)))
        return out


class RapidOcr:
    name = "rapidocr"

    def __init__(self) -> None:
        from rapidocr_onnxruntime import RapidOCR

        self._eng = RapidOCR()

    def read(self, image: np.ndarray) -> list[OcrText]:
        res, _ = self._eng(image)
        return [OcrText(str(r[1]), float(r[2])) for r in (res or [])]


class NullOcr:
    """Used when no engine is installed: reads nothing and says so once."""

    name = "none"

    def read(self, image: np.ndarray) -> list[OcrText]:
        return []


def make_ocr(name: str = "auto") -> OcrEngine:
    order = [name] if name != "auto" else (["apple_vision", "rapidocr"] if sys.platform == "darwin" else ["rapidocr"])
    for n in order:
        try:
            if n == "apple_vision":
                import Vision  # noqa: F401

                return VisionOcr()
            if n == "rapidocr":
                return RapidOcr()
        except Exception as exc:  # noqa: BLE001
            log.info("ocr engine %s unavailable: %s", n, exc)
    log.warning("no OCR engine installed (uv sync --extra ocr); price tags will not be read")
    return NullOcr()


def read_price_tags(frame: np.ndarray, tags: list[dict[str, Any]], engine: OcrEngine) -> list[PriceRead]:
    """tags: [{tag: 'A1-milk', polygon: [[x,y],...] normalised}] -> one PriceRead per tag (price None when unreadable)."""
    h, w = frame.shape[:2]
    out = []
    for t in tags:
        xs = [int(x * w) for x, _ in t["polygon"]]
        ys = [int(y * h) for _, y in t["polygon"]]
        x1, x2, y1, y2 = max(0, min(xs)), min(w, max(xs)), max(0, min(ys)), min(h, max(ys))
        if x2 - x1 < 8 or y2 - y1 < 8:
            out.append(PriceRead(t["tag"], "", None, 0.0, engine.name))
            continue
        texts = engine.read(frame[y1:y2, x1:x2])
        joined = " ".join(x.text for x in texts)
        price = parse_price(joined)
        conf = float(np.mean([x.conf for x in texts])) if texts else 0.0
        out.append(PriceRead(t["tag"], joined, price, round(conf, 3), engine.name))
    return out
