"""Workspace module — project-local focus and preferences."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import IntelligenceModule, ModuleContext


def _bullet_block(title: str, items: Any) -> List[str]:
    if not isinstance(items, list) or not items:
        return []
    lines = [f"{title}:"]
    for item in items:
        text = str(item).strip()
        if text:
            lines.append(f"- {text}")
    return lines if len(lines) > 1 else []


class WorkspaceModule(IntelligenceModule):
    name = "workspace"
    priority = 30

    def build_context(self, ctx: ModuleContext) -> Optional[str]:
        workspace = ctx.bundle.get("workspace") or {}
        if not workspace:
            return None

        label = (workspace.get("label") or "").strip()
        if not label and ctx.cwd:
            label = Path(ctx.cwd).name

        lines: List[str] = ["[mstrmnd:workspace]"]
        if label:
            lines.append(f"Workspace: {label}")

        lines.extend(_bullet_block("Focus", workspace.get("focus")))
        lines.extend(_bullet_block("Prefer", workspace.get("prefer")))
        lines.extend(_bullet_block("Avoid", workspace.get("avoid")))

        # Surface which declared context files exist (paths only — content
        # is already loaded by Hermes via AGENTS.md / SOUL.md).
        declared = workspace.get("context_paths") or []
        if isinstance(declared, list) and ctx.cwd:
            present = []
            missing = []
            root = Path(ctx.cwd)
            for rel in declared:
                rel_s = str(rel).strip()
                if not rel_s:
                    continue
                if (root / rel_s).is_file():
                    present.append(rel_s)
                else:
                    missing.append(rel_s)
            if present:
                lines.append("Context present: " + ", ".join(present))
            if missing:
                lines.append("Context missing: " + ", ".join(missing))

        if len(lines) <= 1:
            return None
        return "\n".join(lines)

    def describe(self, ctx: ModuleContext) -> Dict[str, Any]:
        workspace = ctx.bundle.get("workspace") or {}
        return {
            **super().describe(ctx),
            "has_config": bool(workspace),
            "label": (workspace.get("label") or "").strip()
            or (Path(ctx.cwd).name if ctx.cwd else ""),
            "focus_count": len(workspace.get("focus") or [])
            if isinstance(workspace.get("focus"), list)
            else 0,
        }
