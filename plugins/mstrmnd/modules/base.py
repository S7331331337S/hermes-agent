"""Base types for mstrmnd intelligence modules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ModuleContext:
    """Per-turn / per-session snapshot passed to modules."""

    session_id: str = ""
    task_id: str = ""
    user_message: str = ""
    is_first_turn: bool = False
    model: str = ""
    platform: str = ""
    cwd: str = ""
    bundle: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Session-scoped flags the layer maintains
    injected_this_session: bool = False


@dataclass
class ToolGate:
    """Optional pre_tool_call decision from a policy module."""

    action: str  # "allow" | "block"
    message: str = ""


class IntelligenceModule(ABC):
    """Pluggable unit of the mstrmnd intelligence layer.

    Modules are fail-open: exceptions are caught by the layer and never
    abort the operator loop. Prefer small, composable modules over a
    single god-object.
    """

    name: str = "base"
    # Lower runs first when composing context.
    priority: int = 100
    enabled: bool = True

    def on_session_start(self, ctx: ModuleContext) -> None:
        """Warm caches / log readiness. Default no-op."""

    def on_session_end(self, ctx: ModuleContext) -> None:
        """Release per-session state. Default no-op."""

    @abstractmethod
    def build_context(self, ctx: ModuleContext) -> Optional[str]:
        """Return ephemeral user-message context, or None to skip."""

    def gate_tool(
        self,
        ctx: ModuleContext,
        tool_name: str,
        args: Any,
    ) -> Optional[ToolGate]:
        """Optionally block a tool call. Default allow."""
        return None

    def describe(self, ctx: ModuleContext) -> Dict[str, Any]:
        """Status payload for ``/mstrmnd status``."""
        return {
            "name": self.name,
            "priority": self.priority,
            "enabled": self.enabled,
        }
