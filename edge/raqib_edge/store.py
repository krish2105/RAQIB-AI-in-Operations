"""SQLite event log and clip writer.

The edge box is offline-first: every event lands here before anything is
sent. `synced_at` is NULL until the cloud acknowledges the id. ULID ids are
unique so replays are harmless.

`ClipWriter` keeps a ring buffer of the last `pre_s` seconds of (blurred)
frames and, when triggered, writes a `pre_s + post_s` clip around the event.
"""

from __future__ import annotations

import json
import sqlite3
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from .events import Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  site TEXT NOT NULL,
  camera TEXT NOT NULL,
  ts TEXT NOT NULL,
  kind TEXT NOT NULL,
  severity INTEGER NOT NULL,
  payload TEXT NOT NULL,
  clip_path TEXT,
  rule_id TEXT NOT NULL,
  synced_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_synced ON events(synced_at);
CREATE INDEX IF NOT EXISTS ix_events_ts ON events(ts);
CREATE TABLE IF NOT EXISTS health (
  ts TEXT NOT NULL, camera TEXT NOT NULL, status TEXT NOT NULL, detail TEXT
);
"""


class EventStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)

    def append(self, e: Event) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO events (id, site, camera, ts, kind, severity, payload, clip_path, rule_id)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (
                e.id,
                e.site,
                e.camera,
                e.ts.astimezone(UTC).isoformat(),
                e.kind,
                e.severity,
                json.dumps(e.payload, default=str),
                e.clip_path,
                e.rule_id,
            ),
        )
        self._conn.commit()

    def set_clip(self, event_id: str, clip_path: str) -> None:
        self._conn.execute("UPDATE events SET clip_path=? WHERE id=?", (clip_path, event_id))
        self._conn.commit()

    def unsynced(self, limit: int = 100) -> list[Event]:
        rows = self._conn.execute(
            "SELECT id, site, camera, ts, kind, severity, payload, clip_path, rule_id FROM events"
            " WHERE synced_at IS NULL ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def mark_synced(self, ids: list[str]) -> None:
        if not ids:
            return
        now = datetime.now(UTC).isoformat()
        self._conn.executemany("UPDATE events SET synced_at=? WHERE id=?", [(now, i) for i in ids])
        self._conn.commit()

    def recent(self, n: int = 50) -> list[Event]:
        rows = self._conn.execute(
            "SELECT id, site, camera, ts, kind, severity, payload, clip_path, rule_id FROM events"
            " ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def count(self) -> int:
        return int(self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def health(self, camera: str, status: str, detail: str | None = None) -> None:
        self._conn.execute(
            "INSERT INTO health (ts, camera, status, detail) VALUES (?,?,?,?)",
            (datetime.now(UTC).isoformat(), camera, status, detail),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_event(r: tuple) -> Event:
        return Event(
            id=r[0],
            site=r[1],
            camera=r[2],
            ts=datetime.fromisoformat(r[3]),
            kind=r[4],
            severity=r[5],
            payload=json.loads(r[6]),
            clip_path=r[7],
            rule_id=r[8],
        )

    def close(self) -> None:
        self._conn.close()


class ClipWriter:
    """Ring buffer of recent frames; writes a clip around a trigger.

    Frames pushed here must already be face-blurred (pipeline guarantees it).
    """

    def __init__(self, out_dir: str | Path, fps: float, pre_s: float = 5.0, post_s: float = 5.0) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.fps = max(1.0, fps)
        self.pre_n = int(pre_s * self.fps)
        self.post_n = int(post_s * self.fps)
        self._buf: deque[np.ndarray] = deque(maxlen=self.pre_n)
        self._pending: list[tuple[str, list[np.ndarray], int]] = []  # (event_id, frames, remaining)

    def push(self, frame: np.ndarray) -> list[tuple[str, str]]:
        """Add a frame. Returns [(event_id, clip_path)] for any clips completed by this frame."""
        self._buf.append(frame)
        done: list[tuple[str, str]] = []
        still: list[tuple[str, list[np.ndarray], int]] = []
        for event_id, frames, remaining in self._pending:
            frames.append(frame)
            remaining -= 1
            if remaining <= 0:
                done.append((event_id, self._write(event_id, frames)))
            else:
                still.append((event_id, frames, remaining))
        self._pending = still
        return done

    def trigger(self, event_id: str) -> None:
        self._pending.append((event_id, list(self._buf), self.post_n))

    def _write(self, event_id: str, frames: list[np.ndarray]) -> str:
        path = self.out_dir / f"{event_id}.mp4"
        h, w = frames[0].shape[:2]
        writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), self.fps, (w, h))
        for f in frames:
            writer.write(f)
        writer.release()
        return str(path)
