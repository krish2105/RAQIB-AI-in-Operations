"""Push unsynced events and their clips to the cloud API.

Idempotent by construction: the API upserts on event id, so a batch that was
delivered but whose acknowledgement was lost is simply re-sent. Events are
marked synced only after a 2xx. Clips are uploaded after their event.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

from .store import EventStore

log = logging.getLogger(__name__)


class Syncer:
    def __init__(
        self,
        store: EventStore,
        api_url: str,
        client: httpx.Client | None = None,
        batch: int = 100,
        timeout: float = 10.0,
    ) -> None:
        self.store = store
        self.api_url = api_url.rstrip("/")
        self.client = client or httpx.Client(timeout=timeout)
        self.batch = batch
        self.online = True
        self._clips_pending: dict[str, str] = {}

    def queue_clip(self, event_id: str, path: str) -> None:
        self._clips_pending[event_id] = path

    def push_once(self) -> int:
        """Send one batch. Returns number of events acknowledged; 0 when offline."""
        events = self.store.unsynced(self.batch)
        sent = 0
        if events:
            try:
                r = self.client.post(
                    f"{self.api_url}/events/batch", json={"events": [e.to_dict() for e in events]}
                )
                r.raise_for_status()
                self.store.mark_synced([e.id for e in events])
                sent = len(events)
                if not self.online:
                    log.info("back online, synced %d events", sent)
                self.online = True
            except (httpx.HTTPError, OSError) as exc:
                if self.online:
                    log.warning("sync offline: %s", exc)
                self.online = False
                return 0
        self._push_clips()
        return sent

    def _push_clips(self) -> None:
        for event_id, path in list(self._clips_pending.items()):
            p = Path(path)
            if not p.exists():
                continue
            try:
                with p.open("rb") as fh:
                    r = self.client.put(
                        f"{self.api_url}/clips/{event_id}", files={"file": (p.name, fh, "video/mp4")}
                    )
                r.raise_for_status()
                del self._clips_pending[event_id]
            except (httpx.HTTPError, OSError) as exc:
                log.warning("clip upload deferred for %s: %s", event_id, exc)
                self.online = False
                return
