"""Edge evaluation report -> docs/results/edge_eval.json

Measures what can be measured without licensed datasets:
  * detector latency (p50/p95) and fps per detector on the demo clip, device
  * detections per class on the fixture frames
  * end-to-end frame->event latency of the pipeline
  * PPE mAP50 if fine-tuned weights + SH17 are present (else reported as "not run" with reason)
Usage: uv run python training/eval.py [--frames 150]
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[2]
RESULTS = REPO / "docs" / "results"
FIXTURES = REPO / "edge" / "tests" / "fixtures" / "frames"
SITE = REPO / "edge" / "sites" / "retail_demo.yaml"
sys.path.insert(0, str(Path(__file__).parent))
from prepare_data import SPECS, check  # noqa: E402


def detector_latency(name: str, frames: list[np.ndarray]) -> dict:
    from raqib_edge.detectors import make_detector

    det = make_detector(name)  # type: ignore[arg-type]
    det.detect(frames[0])  # warm-up
    lat, per_class = [], {}
    for im in frames:
        t0 = time.perf_counter()
        dets = det.detect(im)
        lat.append((time.perf_counter() - t0) * 1000)
        for d in dets:
            per_class[d.cls] = per_class.get(d.cls, 0) + 1
    arr = np.array(lat)
    return {
        "device": getattr(det, "_device", "?"),
        "latency_ms_p50": round(float(np.percentile(arr, 50)), 1),
        "latency_ms_p95": round(float(np.percentile(arr, 95)), 1),
        "fps_detect_only": round(1000.0 / float(arr.mean()), 1),
        "detections_per_class": per_class,
        "frames": len(frames),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=150)
    args = ap.parse_args(argv)
    fixtures = [cv2.imread(str(p)) for p in sorted(FIXTURES.glob("*.jpg"))]
    cap = cv2.VideoCapture(str(REPO / "edge" / "data" / "video" / "checkout_39221979.mp4"))
    clip_frames = []
    while len(clip_frames) < args.frames:
        ok, f = cap.read()
        if not ok:
            break
        clip_frames.append(f)
    cap.release()

    report: dict = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "machine": platform.platform(),
        "detectors": {},
        "fixtures": {},
        "pipeline": {},
        "ppe_map50": {"status": "not run"},
    }
    for name in ("yolo", "rtdetr"):
        try:
            report["detectors"][name] = detector_latency(name, clip_frames[: min(len(clip_frames), 60 if name == "yolo" else 20)])
            report["fixtures"][name] = detector_latency(name, fixtures)["detections_per_class"]
        except FileNotFoundError as exc:
            report["detectors"][name] = {"status": "weights missing", "detail": str(exc)}

    from raqib_edge.pipeline import run_pipeline

    tmp_db = RESULTS / "_eval_events.db"
    tmp_db.unlink(missing_ok=True)
    stats = run_pipeline(SITE, max_frames=args.frames, detector="yolo", api=None, db_path=tmp_db,
                         clips_dir=RESULTS / "_eval_clips", cameras=["cam1"])
    report["pipeline"] = {
        "frames": stats.frames, "fps_end_to_end": round(stats.fps, 1),
        "frame_to_event_ms_p50": round(stats.latency_ms_p50, 1), "frame_to_event_ms_p95": round(stats.latency_ms_p95, 1),
        "events": stats.events, "events_by_kind": stats.by_kind, "device": stats.device,
    }
    tmp_db.unlink(missing_ok=True)

    ppe_w = REPO / "edge" / "data" / "weights" / "ppe_yolo26n.pt"
    sh17 = check(SPECS["sh17"])
    if ppe_w.exists() and sh17 is not None:
        from ultralytics import YOLO

        from raqib_edge.detectors import pick_device

        m = YOLO(str(ppe_w)).val(data=str(sh17 / "sh17.yaml"), device=pick_device(), verbose=False)
        report["ppe_map50"] = {"status": "ok", "map50": float(m.box.map50), "dataset": "SH17 (CC BY-NC-SA 4.0)"}
    else:
        report["ppe_map50"] = {
            "status": "not run",
            "reason": "requires fine-tuned weights and SH17 (manual download, CC BY-NC-SA 4.0). "
                      "Target >= 0.80 mAP50 is a pilot deliverable, not met by COCO weights.",
        }

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "edge_eval.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
