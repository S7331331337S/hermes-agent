"""Vision module — inject design / north-star intent."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import IntelligenceModule, ModuleContext


class VisionModule(IntelligenceModule):
    name = "vision"
    priority = 10

    def build_context(self, ctx: ModuleContext) -> Optional[str]:
        vision = ctx.bundle.get("vision") or {}
        if not vision:
            return None

        lines: List[str] = ["[mstrmnd:vision]"]
        name = (vision.get("name") or "").strip()
        tagline = (vision.get("tagline") or "").strip()
        if name or tagline:
            header = name or "vision"
            if tagline:
                header = f"{header} — {tagline}"
            lines.append(header)

        principles = vision.get("principles") or []
        if isinstance(principles, list) and principles:
            lines.append("Principles:")
            for item in principles:
                text = str(item).strip()
                if text:
                    lines.append(f"- {text}")

        north = (vision.get("north_star") or "").strip()
        if north:
            # Cap verbosity so we don't drown the user message.
            if len(north) > 1200:
                north = north[:1200].rstrip() + "…"
            lines.append("North star:")
            lines.append(north)

        if len(lines) <= 1:
            return None
        return "\n".join(lines)

    def describe(self, ctx: ModuleContext) -> Dict[str, Any]:
        vision = ctx.bundle.get("vision") or {}
        principles = vision.get("principles") or []
        return {
            **super().describe(ctx),
            "has_config": bool(vision),
            "principle_count": len(principles) if isinstance(principles, list) else 0,
            "name": vision.get("name") or self.name,
        }
