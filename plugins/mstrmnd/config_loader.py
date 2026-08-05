"""Load and deep-merge mstrmnd YAML configs (profile → workspace)."""

from __future__ import annotations

import logging
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from .store import CONFIG_NAMES, iter_existing_configs

logger = logging.getLogger(__name__)


def _load_yaml(path: Path) -> Dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover — hermes always has pyyaml
        raise RuntimeError("PyYAML is required for mstrmnd configs") from exc
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("mstrmnd: failed to parse %s: %s", path, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("mstrmnd: %s root must be a mapping; ignoring", path)
        return {}
    return data


def deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *overlay* into a copy of *base*.

    Lists are replaced (not concatenated) so workspace overlays can fully
    redefine principles / policies without surprising concatenation.
    """
    out = deepcopy(base)
    for key, value in overlay.items():
        if (
            key in out
            and isinstance(out[key], dict)
            and isinstance(value, dict)
        ):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def load_merged_config(name: str, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Merge all existing layers for ``name`` (e.g. ``vision.yaml``)."""
    if name not in CONFIG_NAMES:
        raise ValueError(f"Unknown mstrmnd config: {name}")
    merged: Dict[str, Any] = {}
    for path in iter_existing_configs(name, cwd):
        merged = deep_merge(merged, _load_yaml(path))
    return merged


def load_bundle(cwd: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Return ``{vision, alignment, workspace}`` merged dicts."""
    return {
        "vision": load_merged_config("vision.yaml", cwd),
        "alignment": load_merged_config("alignment.yaml", cwd),
        "workspace": load_merged_config("workspace.yaml", cwd),
    }
