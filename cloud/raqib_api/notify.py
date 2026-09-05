"""Trilingual alert templates. No free text reaches an external channel: only
these templates with validated variables. Missing variables render as "-".
"""

from __future__ import annotations

from pathlib import Path
from string import Formatter
from typing import Any

import yaml

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates" / "alerts"
_cache: dict[str, dict[str, str]] = {}


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "-"


def _load(lang: str) -> dict[str, str]:
    if lang not in _cache:
        p = TEMPLATES_DIR / f"{lang}.yaml"
        if not p.exists():
            raise ValueError(f"no alert templates for language {lang!r}")
        _cache[lang] = yaml.safe_load(p.read_text())
    return _cache[lang]


def render_alert(template: str, lang: str, vars: dict[str, Any]) -> str:
    tpl = _load(lang).get(template)
    if tpl is None:
        raise ValueError(f"unknown alert template {template!r} for {lang!r}")
    clean = {k: ("-" if v is None else str(v)) for k, v in vars.items()}
    return Formatter().vformat(tpl, (), _Safe(clean)).strip()


def available() -> dict[str, list[str]]:
    return {p.stem: sorted(yaml.safe_load(p.read_text()).keys()) for p in sorted(TEMPLATES_DIR.glob("*.yaml"))}
