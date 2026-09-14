"""Configuration loading for the collector CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_settings(path: Path) -> dict[str, Any]:
    """Load the single settings YAML file and fail clearly when malformed."""
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    with path.open("r", encoding="utf-8-sig") as handle:
        data = yaml.safe_load(handle) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Configuration root must be a mapping: {path}")
    return data
