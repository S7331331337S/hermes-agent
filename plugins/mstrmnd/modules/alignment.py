"""Alignment module — soft behavioral guidance for the operator."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import IntelligenceModule, ModuleContext


class AlignmentModule(IntelligenceModule):
    name = "alignment"
    priority = 20

    def build_context(self, ctx: ModuleContext) -> Optional[str]:
        alignment = ctx.bundle.get("alignment") or {}
        guidance = alignment.get("guidance") or []
        if not isinstance(guidance, list) or not guidance:
            return None

        lines: List[str] = ["[mstrmnd:alignment]"]
        for item in guidance:
            text = str(item).strip()
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines) if len(lines) > 1 else None

    def describe(self, ctx: ModuleContext) -> Dict[str, Any]:
        alignment = ctx.bundle.get("alignment") or {}
        guidance = alignment.get("guidance") or []
        policies = alignment.get("policies") or []
        return {
            **super().describe(ctx),
            "inject_mode": alignment.get("inject_mode") or "first_turn",
            "guidance_count": len(guidance) if isinstance(guidance, list) else 0,
            "policy_count": len(policies) if isinstance(policies, list) else 0,
        }
