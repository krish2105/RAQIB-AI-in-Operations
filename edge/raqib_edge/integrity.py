"""Supply-chain check for the detector weights (OWASP ASI04). When RAQIB_WEIGHTS_SHA256 is set, the box refuses
to start unless the weights file on disk hashes to exactly that value. The hash also travels in every heartbeat."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path


class WeightsTampered(SystemExit):
    def __init__(self, path: str, expected: str, actual: str) -> None:
        super().__init__(f"refusing to start: weights {path} sha256 {actual[:12]}… does not match the pinned {expected[:12]}… (RAQIB_WEIGHTS_SHA256)")
        self.path, self.expected, self.actual = path, expected, actual


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_weights(path: str | Path | None, expected: str | None = None) -> str | None:
    """Returns the actual hash. Raises WeightsTampered (a SystemExit) on mismatch. No pin -> no check, hash still returned."""
    expected = expected if expected is not None else os.environ.get("RAQIB_WEIGHTS_SHA256")
    if not path or not Path(path).exists():
        return None
    actual = sha256_file(path)
    if expected and actual.lower() != expected.strip().lower():
        raise WeightsTampered(str(path), expected, actual)
    return actual
