from pathlib import Path

import cv2
import numpy as np

from raqib_edge.capture import FrameSource, blur_faces

CLIP = Path(__file__).resolve().parents[1] / "data" / "video" / "timelapse_854634.mp4"
FRAME = Path(__file__).parent / "fixtures" / "frames" / "checkout_t16.jpg"


def test_file_source_loops_past_end():
    src = FrameSource(str(CLIP), loop=True)
    src.open()
    total = int(cv2.VideoCapture(str(CLIP)).get(cv2.CAP_PROP_FRAME_COUNT))
    n = 0
    for _ts, frame in src.frames():
        assert frame.ndim == 3
        n += 1
        if n > total + 5:
            break
    assert src.loops >= 1
    src.release()


def test_blur_changes_head_region_only():
    img = cv2.imread(str(FRAME))
    # the cashier: box roughly around the woman in the centre
    box = (1080.0, 230.0, 1290.0, 560.0)
    out = blur_faces(img, [box])
    x1, y1, x2, y2 = (int(v) for v in box)
    head = np.abs(out[y1 : y1 + 80, x1:x2].astype(int) - img[y1 : y1 + 80, x1:x2].astype(int)).mean()
    outside = np.abs(out[700:1000, 300:600].astype(int) - img[700:1000, 300:600].astype(int)).mean()
    assert head > 2.0, "head region should be visibly altered"
    assert outside == 0.0, "pixels outside person boxes must be untouched"
    assert out.shape == img.shape


def test_blur_without_face_found_still_blurs_head_band():
    img = np.random.default_rng(0).integers(0, 255, (400, 300, 3), dtype=np.uint8)
    out = blur_faces(img, [(50.0, 50.0, 200.0, 350.0)])
    diff_head = np.abs(out[50:120, 50:200].astype(int) - img[50:120, 50:200].astype(int)).mean()
    diff_legs = np.abs(out[300:350, 50:200].astype(int) - img[300:350, 50:200].astype(int)).mean()
    assert diff_head > 5.0
    assert diff_legs == 0.0
