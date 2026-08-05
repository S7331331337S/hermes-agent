"""Profile- and workspace-aware paths for the mstrmnd intelligence layer."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

CONFIG_NAMES = ("vision.yaml", "alignment.yaml", "workspace.yaml")


def hermes_mstrmnd_dir() -> Path:
    """Return ``$HERMES_HOME/mstrmnd`` (profile-aware)."""
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home() / "mstrmnd"
    except Exception:
        return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "mstrmnd"


def workspace_root(cwd: Optional[str] = None) -> Path:
    return Path(cwd or os.getcwd()).resolve()


def workspace_mstrmnd_dirs(cwd: Optional[str] = None) -> List[Path]:
    """Candidate project-local mstrmnd dirs (first existing wins for init)."""
    root = workspace_root(cwd)
    return [root / ".mstrmnd", root / ".hermes" / "mstrmnd"]


def resolve_workspace_mstrmnd_dir(cwd: Optional[str] = None) -> Optional[Path]:
    for path in workspace_mstrmnd_dirs(cwd):
        if path.is_dir():
            return path
    return None


def config_search_paths(name: str, cwd: Optional[str] = None) -> List[Path]:
    """Ordered paths for a config file: profile base, then workspace overlay."""
    paths = [hermes_mstrmnd_dir() / name]
    ws = resolve_workspace_mstrmnd_dir(cwd)
    if ws is not None:
        paths.append(ws / name)
    else:
        # Still allow reading a not-yet-created preferred overlay location
        # when callers want to show where workspace config *would* live.
        pass
    return paths


def iter_existing_configs(name: str, cwd: Optional[str] = None) -> Iterable[Path]:
    for path in config_search_paths(name, cwd):
        if path.is_file():
            yield path


def plugin_templates_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def ensure_profile_scaffold(force: bool = False) -> List[Path]:
    """Copy default templates into ``$HERMES_HOME/mstrmnd`` if missing.

    Returns the list of paths written (empty when everything already exists
    and ``force`` is false).
    """
    dest_dir = hermes_mstrmnd_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    tmpl_dir = plugin_templates_dir()
    for name in CONFIG_NAMES:
        dest = dest_dir / name
        if dest.exists() and not force:
            continue
        src = tmpl_dir / name
        if not src.is_file():
            continue
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(dest)
    return written


def ensure_workspace_scaffold(
    cwd: Optional[str] = None, force: bool = False
) -> Tuple[Path, List[Path]]:
    """Create ``.mstrmnd/`` under the workspace with template overlays.

    Returns ``(dir, written_paths)``.
    """
    dest_dir = workspace_mstrmnd_dirs(cwd)[0]
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: List[Path] = []
    tmpl_dir = plugin_templates_dir()
    for name in CONFIG_NAMES:
        dest = dest_dir / name
        if dest.exists() and not force:
            continue
        src = tmpl_dir / name
        if not src.is_file():
            continue
        dest.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        written.append(dest)
    return dest_dir, written
