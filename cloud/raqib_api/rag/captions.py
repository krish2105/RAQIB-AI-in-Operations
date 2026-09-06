"""VLM captions of ≤3 blurred keyframes, strict JSON, quota-capped, never raising.

Frames come from the stored 10 s clip, which the edge blurred before upload. No raw frame ever
reaches this module. A caption is advisory text for retrieval; it never changes severity.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np

from ..config import settings
from ..llm import ProviderChain, Quota, get_provider, try_complete
from ..models import Caption, Event

log = logging.getLogger(__name__)

CAPTION_SCHEMA = {
    "type": "object",
    "properties": {
        "scene": {"type": "string", "maxLength": 400},
        "people_count": {"type": "integer", "minimum": 0, "maximum": 200},
        "actions": {"type": "array", "items": {"type": "string", "maxLength": 120}, "maxItems": 8},
        "risk_notes": {"type": "array", "items": {"type": "string", "maxLength": 160}, "maxItems": 6},
    },
    "required": ["scene", "people_count", "actions", "risk_notes"],
    "additionalProperties": False,
}

SYSTEM = (
    "You describe blurred CCTV keyframes from a retail floor or factory for an operations log. "
    "Faces are blurred by design; never guess identity, age, gender or ethnicity. "
    "Report only what is visible: the scene, how many people, what they are doing, and any safety or "
    "service risk (blocked exit, long queue, empty shelf, missing helmet). Reply with JSON only."
)


def extract_keyframes(clip_path: str | Path | None, n: int | None = None) -> list[np.ndarray]:
    """Evenly spaced frames from the stored clip. [] when the clip or the decoder is missing."""
    n = n or settings.caption_max_frames
    if not clip_path or not Path(clip_path).exists():
        return []
    try:
        import cv2
    except ImportError:  # pragma: no cover — Render has no decoder; indexing runs on the Mac
        log.info("cv2 not installed; no keyframes for %s", clip_path)
        return []
    cap = cv2.VideoCapture(str(clip_path))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frames: list[np.ndarray] = []
    if total <= 0:
        cap.release()
        return frames
    for i in range(n):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((i + 0.5) * total / n))
        ok, frame = cap.read()
        if ok and frame is not None:
            frames.append(frame)
    cap.release()
    return frames[:n]


def frames_to_jpeg(frames: list[np.ndarray], max_side: int = 768) -> list[bytes]:
    import cv2

    out = []
    for f in frames:
        h, w = f.shape[:2]
        s = min(1.0, max_side / max(h, w))
        if s < 1.0:
            f = cv2.resize(f, (int(w * s), int(h * s)))
        ok, buf = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            out.append(bytes(buf))
    return out


def caption_event(event: Event, frames: list[np.ndarray], provider: ProviderChain | None = None,
                  quota: Quota | None = None, jpegs: list[bytes] | None = None) -> Caption:
    """Always returns a Caption row. model='none' + parsed.reason records why nothing was captioned."""
    base = Caption(event_id=event.id, site=event.site, camera=event.camera, ts=event.ts)
    frames = list(frames)[: settings.caption_max_frames]
    if not frames and not jpegs:
        base.parsed = {"reason": "no_frames"}
        return base
    quota = quota if quota is not None else Quota.default()
    if quota.limit("caption") and not quota.check("caption"):
        log.warning("quota_exhausted: captions for %s skipped (CAPTION_DAILY_REQUESTS=%s)", event.site, settings.caption_daily_requests)
        base.parsed = {"reason": "quota_exhausted"}
        return base
    images = jpegs if jpegs is not None else frames_to_jpeg(frames)
    images = images[: settings.caption_max_frames]
    provider = provider or get_provider("caption", quota=quota)
    user = (f"<event kind={event.kind} rule={event.rule_id} severity={event.severity} zone={event.payload.get('zone', '-')}>"
            f" {len(images)} keyframes attached. Describe them.")
    res = try_complete(provider, SYSTEM, user, json_schema=CAPTION_SCHEMA, images=images, max_tokens=400)
    if res is None:
        base.parsed = {"reason": "provider_unavailable"}
        return base
    if quota.limit("caption"):
        quota.record("caption", res.tokens_in + res.tokens_out)
    base.frames = len(images)
    base.model, base.provider = res.model, res.provider
    base.tokens_in, base.tokens_out, base.cost_usd = res.tokens_in, res.tokens_out, res.cost_usd
    if res.parsed is None:
        base.parsed = {"reason": "invalid_json", "error": res.schema_error}
        base.text = ""
        return base
    base.parsed = res.parsed
    base.text = caption_text(res.parsed)
    return base


def caption_text(parsed: dict[str, Any]) -> str:
    bits = [str(parsed.get("scene", "")).strip()]
    if parsed.get("people_count") is not None:
        bits.append(f"{parsed['people_count']} people visible")
    if parsed.get("actions"):
        bits.append("actions: " + "; ".join(map(str, parsed["actions"])))
    if parsed.get("risk_notes"):
        bits.append("risks: " + "; ".join(map(str, parsed["risk_notes"])))
    return ". ".join(b for b in bits if b)
