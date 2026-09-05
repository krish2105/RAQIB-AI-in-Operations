"""OpenCV preview: zones, tracks, blurred heads, and the last events. Dev only."""

from __future__ import annotations

import cv2
import numpy as np

ZONE_COLOURS = {
    "entrance": (180, 180, 180),
    "queue": (0, 200, 255),
    "checkout": (185, 209, 31),
    "shelf": (255, 160, 60),
    "work_area": (150, 150, 150),
    "exclusion": (61, 77, 255),
    "machine": (32, 176, 255),
}
SEV_COLOURS = {1: (181, 141, 110), 2: (0, 183, 245), 3: (61, 77, 255)}


class PreviewWindow:
    def __init__(self, title: str = "RAQIB edge preview  (q to quit)") -> None:
        self.title = title
        self._recent: list[str] = []

    def render(self, worker, stats) -> bool:
        frame = worker.last_frame.copy()
        wh = (frame.shape[1], frame.shape[0])
        for z in worker.site.zones_for(worker.cam.name):
            pts = np.array(z.pixel_polygon(wh), dtype=np.int32)
            cv2.polylines(frame, [pts], True, ZONE_COLOURS.get(z.kind, (200, 200, 200)), 2)
            cv2.putText(frame, z.name, tuple(pts[0] + [4, 18]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, ZONE_COLOURS.get(z.kind, (200, 200, 200)), 1)
        for t in worker.last_tracks:
            x1, y1, x2, y2 = (int(v) for v in t.xyxy)
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 255, 255), 1)
            cv2.putText(frame, f"#{t.track_id} {t.conf:.2f}", (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        for e in worker.last_events:
            self._recent.insert(0, f"{e.rule_id} sev{e.severity} {e.kind} {e.payload.get('count', e.payload.get('track_id', ''))}")
        self._recent = self._recent[:6]
        hud = f"{worker.cam.name}  {stats.fps or 0:.1f} fps  frames {stats.frames}  events {stats.events}  {stats.detector}/{stats.device}"
        cv2.rectangle(frame, (0, 0), (wh[0], 26), (11, 13, 16), -1)
        cv2.putText(frame, hud, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (232, 234, 237), 1)
        for i, line in enumerate(self._recent):
            sev = int(line.split("sev")[1][0]) if "sev" in line else 1
            cv2.putText(frame, line, (8, 50 + 20 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, SEV_COLOURS.get(sev, (200, 200, 200)), 1)
        cv2.imshow(self.title, frame)
        return (cv2.waitKey(1) & 0xFF) != ord("q")

    def close(self) -> None:
        cv2.destroyAllWindows()
