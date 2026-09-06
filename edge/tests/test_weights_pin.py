"""ASI04 supply chain: tampered weights (hash mismatch against the pin) -> the edge refuses to start."""

from __future__ import annotations

import pytest

from raqib_edge.integrity import WeightsTampered, sha256_file, verify_weights


def test_matching_pin_passes_and_mismatch_refuses_to_start(tmp_path, monkeypatch):
    w = tmp_path / "yolo.pt"
    w.write_bytes(b"real weights " * 1000)
    good = sha256_file(w)
    assert verify_weights(w, expected=good) == good
    assert verify_weights(w, expected=None) == good  # no pin -> no enforcement, hash still reported
    monkeypatch.setenv("RAQIB_WEIGHTS_SHA256", good.upper())
    assert verify_weights(w) == good  # env pin, case-insensitive
    w.write_bytes(b"tampered weights " * 1000)
    with pytest.raises(WeightsTampered) as exc:
        verify_weights(w)
    assert isinstance(exc.value, SystemExit) and "refusing to start" in str(exc.value) and exc.value.expected == good.upper()
    assert verify_weights(tmp_path / "missing.pt", expected=good) is None
