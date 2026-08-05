"""Policy module — optional hard gates on tool calls."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from .base import IntelligenceModule, ModuleContext, ToolGate


def _args_blob(args: Any) -> str:
    if args is None:
        return ""
    if isinstance(args, str):
        return args
    try:
        return json.dumps(args, ensure_ascii=False, default=str)
    except Exception:
        return str(args)


class PolicyModule(IntelligenceModule):
    name = "policy"
    priority = 40

    def build_context(self, ctx: ModuleContext) -> Optional[str]:
        # Soft context for active policies is optional; keep quiet unless
        # there is at least one block policy so the model knows the rules.
        alignment = ctx.bundle.get("alignment") or {}
        policies = alignment.get("policies") or []
        if not isinstance(policies, list):
            return None
        blocks = [
            p
            for p in policies
            if isinstance(p, dict) and str(p.get("action", "")).lower() == "block"
        ]
        if not blocks:
            return None
        lines = ["[mstrmnd:policy]", "Active block policies:"]
        for p in blocks:
            pid = str(p.get("id") or "policy").strip()
            match = str(p.get("match") or "").strip()
            tools = p.get("tools") or []
            tool_s = (
                ",".join(str(t) for t in tools)
                if isinstance(tools, list)
                else str(tools)
            )
            lines.append(f"- {pid}: tools=[{tool_s}] match={match!r}")
        return "\n".join(lines)

    def gate_tool(
        self,
        ctx: ModuleContext,
        tool_name: str,
        args: Any,
    ) -> Optional[ToolGate]:
        alignment = ctx.bundle.get("alignment") or {}
        policies = alignment.get("policies") or []
        if not isinstance(policies, list):
            return None

        blob = _args_blob(args)
        tool = (tool_name or "").strip()

        for policy in policies:
            if not isinstance(policy, dict):
                continue
            action = str(policy.get("action") or "block").lower()
            if action != "block":
                continue
            tools = policy.get("tools") or []
            if isinstance(tools, list) and tools:
                allowed = {str(t).strip() for t in tools}
                if tool not in allowed:
                    continue
            match = str(policy.get("match") or "").strip()
            if match and match not in blob:
                continue
            if not match and not tools:
                continue
            message = (
                str(policy.get("message") or "").strip()
                or f"Blocked by mstrmnd policy '{policy.get('id') or 'unnamed'}'."
            )
            return ToolGate(action="block", message=message)
        return None

    def describe(self, ctx: ModuleContext) -> Dict[str, Any]:
        alignment = ctx.bundle.get("alignment") or {}
        policies = alignment.get("policies") or []
        block_count = 0
        if isinstance(policies, list):
            block_count = sum(
                1
                for p in policies
                if isinstance(p, dict) and str(p.get("action", "")).lower() == "block"
            )
        return {
            **super().describe(ctx),
            "block_policies": block_count,
        }
