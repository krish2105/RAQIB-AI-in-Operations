"""Pipeline glue: source -> detector.track -> blur -> rules -> store/clips -> sync.

One camera per `CameraWorker`. `run_pipeline` drives one or more cameras from a
site config in a single process (the demo box has two file cameras). Frames are
blurred immediately after tracking and before anything else sees them.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from .capture import FrameSource, blur_faces
from .detectors import Detector, make_detector
from .events import Event
from .machine_state import MachineStateTracker
from .rules import RuleState, evaluate
from .shelf import shelf_empty_ratio
from .store import ClipWriter, EventStore
from .sync import Syncer
from .zones import CameraCfg, Site, load_site

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Stats:
    frames: int = 0
    events: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    fps: float = 0.0
    device: str = ""
    detector: str = ""
    latency_ms_p50: float = 0.0
    latency_ms_p95: float = 0.0
    clips: int = 0
    synced: int = 0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _resolve_uri(cam: CameraCfg) -> str | int:
    if cam.source == "webcam":
        return int(cam.uri) if str(cam.uri).isdigit() else 0
    if cam.source == "file":
        p = Path(cam.uri)
        return str(p if p.is_absolute() else REPO_ROOT / p)
    return str(cam.uri)


class CameraWorker:
    def __init__(
        self,
        site: Site,
        cam: CameraCfg,
        detector: Detector,
        store: EventStore,
        clips_dir: Path,
        syncer: Syncer | None,
        source_override: str | None = None,
        shelf_every: int = 15,
    ) -> None:
        self.site = site
        self.cam = cam
        self.detector = detector
        self.store = store
        self.syncer = syncer
        self.state = RuleState()
        self.machines = MachineStateTracker()
        self.shelf_every = shelf_every
        uri = 0 if source_override == "webcam" else _resolve_uri(cam)
        self.source = FrameSource(uri, loop=True, target_fps=None)
        self.source.open()
        self.clips = ClipWriter(clips_dir, fps=min(self.source.fps, 15.0), pre_s=5, post_s=5)
        self._n = 0
        self._shelf_cache: dict[str, float] = {}
        self._clip_stride = max(1, int(round(self.source.fps / self.clips.fps)))
        self.last_frame: np.ndarray | None = None
        self.last_tracks: list = []
        self.last_events: list[Event] = []

    def step(self, ts: datetime, frame: np.ndarray) -> list[Event]:
        self._n += 1
        wh = (frame.shape[1], frame.shape[0])
        tracks = self.detector.track(frame)
        # ---- privacy gate: nothing below this line sees an unblurred frame
        safe = blur_faces(frame, [t.xyxy for t in tracks if t.cls == "person"])
        frame = None  # noqa: F841  (make the intent explicit)

        shelf_ratios: dict[str, float] | None = None
        if self.site.profile == "retail" and self._n % self.shelf_every == 1:
            for z in self.site.zones_for(self.cam.name, "shelf"):
                self._shelf_cache[z.name] = shelf_empty_ratio(safe, z.polygon)
        if self._shelf_cache:
            shelf_ratios = dict(self._shelf_cache)

        machine_states: dict[str, str] | None = None
        if self.site.profile == "factory":
            machine_states = {}
            for z in self.site.zones_for(self.cam.name, "machine"):
                x1, y1, x2, y2 = _bbox_px(z.polygon, wh)
                machine_states[z.name] = self.machines.update(z.name, safe[y1:y2, x1:x2])

        events = evaluate(
            tracks,
            self.site,
            self.cam.name,
            self.state,
            ts,
            frame_wh=wh,
            shelf_ratios=shelf_ratios,
            machine_states=machine_states,
        )
        for e in events:
            self.store.append(e)
            if e.severity >= 2:
                self.clips.trigger(e.id)
        if self._n % self._clip_stride == 0:
            for event_id, path in self.clips.push(safe):
                self.store.set_clip(event_id, path)
                if self.syncer:
                    self.syncer.queue_clip(event_id, path)
        self.last_frame, self.last_tracks, self.last_events = safe, tracks, events
        return events


def _bbox_px(poly, wh):
    xs = [p[0] * wh[0] for p in poly]
    ys = [p[1] * wh[1] for p in poly]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def run_pipeline(
    site: Site | str | Path,
    max_frames: int | None = None,
    detector: str = "yolo",
    api: str | None = None,
    db_path: str | Path | None = None,
    clips_dir: str | Path | None = None,
    preview: bool = False,
    source_override: str | None = None,
    cameras: list[str] | None = None,
    sync_every_s: float = 2.0,
) -> Stats:
    site = load_site(site) if not isinstance(site, Site) else site
    data_dir = REPO_ROOT / "edge" / "data"
    store = EventStore(db_path or data_dir / "events.db")
    clips_dir = Path(clips_dir or data_dir / "clips")
    det = make_detector(detector)  # type: ignore[arg-type]
    syncer = Syncer(store, api) if api else None
    cam_names = cameras or list(site.cameras)
    workers = [
        CameraWorker(site, site.cameras[c], det, store, clips_dir, syncer, source_override)
        for c in cam_names
    ]
    if source_override == "webcam":
        workers = workers[:1]
    stats = Stats(device=getattr(det, "_device", "?"), detector=det.name)
    lat: list[float] = []
    t_start = time.perf_counter()
    last_sync = t_start
    iters = [w.source.frames() for w in workers]
    show = None
    if preview:
        from .preview import PreviewWindow

        show = PreviewWindow()
    try:
        while True:
            for w, it in zip(workers, iters, strict=True):
                try:
                    ts, frame = next(it)
                except StopIteration:
                    return stats
                t0 = time.perf_counter()
                events = w.step(ts, frame)
                lat.append((time.perf_counter() - t0) * 1000)
                stats.frames += 1
                for e in events:
                    stats.events += 1
                    stats.by_kind[e.kind] = stats.by_kind.get(e.kind, 0) + 1
                    log.info("event %s sev%d %s %s", e.rule_id, e.severity, e.kind, e.payload)
                if show is not None and w.last_frame is not None and not show.render(w, stats):
                    return stats
            if syncer and time.perf_counter() - last_sync >= sync_every_s:
                stats.synced += syncer.push_once()
                last_sync = time.perf_counter()
            if max_frames is not None and stats.frames >= max_frames:
                break
    finally:
        elapsed = time.perf_counter() - t_start
        stats.fps = stats.frames / elapsed if elapsed > 0 else 0.0
        if lat:
            arr = np.array(lat)
            stats.latency_ms_p50 = float(np.percentile(arr, 50))
            stats.latency_ms_p95 = float(np.percentile(arr, 95))
        stats.clips = len(list(clips_dir.glob("*.mp4"))) if clips_dir.exists() else 0
        if syncer:
            stats.synced += syncer.push_once()
        for w in workers:
            w.source.release()
        if show is not None:
            show.close()
    return stats
