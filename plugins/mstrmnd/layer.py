"""IntelligenceLayer — orchestrates mstrmnd modules between harness and operator."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .config_loader import load_bundle
from .modules import BUILTIN_MODULES, IntelligenceModule, ModuleContext, ToolGate
from .store import (
    ensure_profile_scaffold,
    hermes_mstrmnd_dir,
    resolve_workspace_mstrmnd_dir,
)

logger = logging.getLogger(__name__)


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class SessionState:
    injected: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)


class IntelligenceLayer:
    """Cache-safe intelligence wrapper used by plugin hooks.

    Responsibilities:
    - Load/merge vision + alignment + workspace configs
    - Compose ephemeral ``pre_llm_call`` context from modules
    - Apply optional ``pre_tool_call`` policy gates
    - Expose status for slash / CLI surfaces

    Non-goals (by design — leave to Hermes core):
    - Mutating the system prompt
    - Replacing AGENTS.md / SOUL.md loading
    - Owning memory or context compression
    """

    def __init__(self, modules: Optional[List[IntelligenceModule]] = None) -> None:
        self._lock = threading.RLock()
        self._modules: List[IntelligenceModule] = list(modules or BUILTIN_MODULES)
        self._bundle: Dict[str, Dict[str, Any]] = {
            "vision": {},
            "alignment": {},
            "workspace": {},
        }
        self._cwd: str = os.getcwd()
        self._sessions: Dict[str, SessionState] = {}
        self._loaded = False

    # -- lifecycle ------------------------------------------------------------

    def reload(self, cwd: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            self._cwd = cwd or os.getcwd()
            try:
                self._bundle = load_bundle(self._cwd)
            except Exception as exc:
                logger.warning("mstrmnd: reload failed: %s", exc)
                self._bundle = {"vision": {}, "alignment": {}, "workspace": {}}
            self._loaded = True
            return dict(self._bundle)

    def ensure_loaded(self, cwd: Optional[str] = None) -> None:
        if not self._loaded or (cwd and cwd != self._cwd):
            self.reload(cwd)

    def register_module(self, module: IntelligenceModule) -> None:
        with self._lock:
            # Replace same-named modules so overlays can swap implementations.
            self._modules = [m for m in self._modules if m.name != module.name]
            self._modules.append(module)
            self._modules.sort(key=lambda m: m.priority)

    def modules(self) -> List[IntelligenceModule]:
        with self._lock:
            return sorted(self._modules, key=lambda m: m.priority)

    # -- session helpers ------------------------------------------------------

    def _session_key(self, session_id: str, task_id: str = "") -> str:
        return session_id or task_id or "default"

    def _state(self, session_id: str, task_id: str = "") -> SessionState:
        key = self._session_key(session_id, task_id)
        with self._lock:
            if key not in self._sessions:
                self._sessions[key] = SessionState()
            return self._sessions[key]

    def _make_ctx(self, **kwargs: Any) -> ModuleContext:
        self.ensure_loaded(kwargs.get("cwd"))
        state = self._state(
            str(kwargs.get("session_id") or ""),
            str(kwargs.get("task_id") or ""),
        )
        return ModuleContext(
            session_id=str(kwargs.get("session_id") or ""),
            task_id=str(kwargs.get("task_id") or ""),
            user_message=str(kwargs.get("user_message") or ""),
            is_first_turn=bool(kwargs.get("is_first_turn")),
            model=str(kwargs.get("model") or ""),
            platform=str(kwargs.get("platform") or ""),
            cwd=self._cwd,
            bundle=dict(self._bundle),
            injected_this_session=state.injected,
        )

    def _inject_mode(self) -> str:
        alignment = self._bundle.get("alignment") or {}
        mode = str(alignment.get("inject_mode") or "first_turn").strip().lower()
        if mode not in {"first_turn", "every_turn", "never"}:
            return "first_turn"
        return mode

    def should_inject(self, is_first_turn: bool, session_id: str, task_id: str = "") -> bool:
        if _truthy("MSTRMND_DISABLE"):
            return False
        mode = self._inject_mode()
        if mode == "never":
            return False
        if mode == "every_turn":
            return True
        # first_turn
        state = self._state(session_id, task_id)
        return is_first_turn or not state.injected

    # -- hook entry points ----------------------------------------------------

    def on_session_start(self, **kwargs: Any) -> None:
        if _truthy("MSTRMND_DISABLE"):
            return
        # Seed profile templates on first use (never overwrites).
        try:
            ensure_profile_scaffold(force=False)
        except Exception as exc:
            logger.debug("mstrmnd: scaffold skipped: %s", exc)
        ctx = self._make_ctx(**kwargs)
        for mod in self.modules():
            if not mod.enabled:
                continue
            try:
                mod.on_session_start(ctx)
            except Exception as exc:
                logger.warning("mstrmnd module %s on_session_start failed: %s", mod.name, exc)

    def on_session_end(self, **kwargs: Any) -> None:
        ctx = self._make_ctx(**kwargs)
        for mod in self.modules():
            if not mod.enabled:
                continue
            try:
                mod.on_session_end(ctx)
            except Exception as exc:
                logger.warning("mstrmnd module %s on_session_end failed: %s", mod.name, exc)
        key = self._session_key(
            str(kwargs.get("session_id") or ""),
            str(kwargs.get("task_id") or ""),
        )
        with self._lock:
            self._sessions.pop(key, None)

    def build_pre_llm_context(self, **kwargs: Any) -> Optional[Dict[str, str]]:
        """Compose ephemeral context for ``pre_llm_call`` (user-message inject)."""
        if _truthy("MSTRMND_DISABLE"):
            return None
        is_first = bool(kwargs.get("is_first_turn"))
        session_id = str(kwargs.get("session_id") or "")
        task_id = str(kwargs.get("task_id") or "")
        if not self.should_inject(is_first, session_id, task_id):
            return None

        ctx = self._make_ctx(**kwargs)
        parts: List[str] = []
        for mod in self.modules():
            if not mod.enabled:
                continue
            try:
                text = mod.build_context(ctx)
            except Exception as exc:
                logger.warning("mstrmnd module %s build_context failed: %s", mod.name, exc)
                continue
            if text and str(text).strip():
                parts.append(str(text).strip())

        if not parts:
            return None

        state = self._state(session_id, task_id)
        state.injected = True
        header = (
            "mstrmnd intelligence layer — alignment context for this turn "
            "(ephemeral; does not alter the system prompt):"
        )
        return {"context": header + "\n\n" + "\n\n".join(parts)}

    def gate_tool(self, tool_name: str, args: Any, **kwargs: Any) -> Optional[Dict[str, str]]:
        """Return a ``pre_tool_call`` block dict, or None to allow."""
        if _truthy("MSTRMND_DISABLE"):
            return None
        ctx = self._make_ctx(**kwargs)
        for mod in self.modules():
            if not mod.enabled:
                continue
            try:
                decision = mod.gate_tool(ctx, tool_name, args)
            except Exception as exc:
                logger.warning("mstrmnd module %s gate_tool failed: %s", mod.name, exc)
                continue
            if isinstance(decision, ToolGate) and decision.action == "block":
                return {
                    "action": "block",
                    "message": decision.message
                    or f"Blocked by mstrmnd module '{mod.name}'.",
                }
        return None

    # -- status / display -----------------------------------------------------

    def status(self, cwd: Optional[str] = None) -> Dict[str, Any]:
        self.ensure_loaded(cwd)
        ws_dir = resolve_workspace_mstrmnd_dir(self._cwd)
        ctx = self._make_ctx(cwd=self._cwd)
        return {
            "enabled": not _truthy("MSTRMND_DISABLE"),
            "profile_dir": str(hermes_mstrmnd_dir()),
            "workspace_dir": str(ws_dir) if ws_dir else None,
            "cwd": self._cwd,
            "inject_mode": self._inject_mode(),
            "modules": [m.describe(ctx) for m in self.modules()],
            "bundle_keys": {
                "vision": sorted((self._bundle.get("vision") or {}).keys()),
                "alignment": sorted((self._bundle.get("alignment") or {}).keys()),
                "workspace": sorted((self._bundle.get("workspace") or {}).keys()),
            },
        }


# Process-wide layer instance used by the plugin hooks.
_LAYER: Optional[IntelligenceLayer] = None
_LAYER_LOCK = threading.Lock()


def get_layer() -> IntelligenceLayer:
    global _LAYER
    with _LAYER_LOCK:
        if _LAYER is None:
            _LAYER = IntelligenceLayer()
        return _LAYER


def reset_layer_for_tests() -> None:
    """Test helper — drop the singleton."""
    global _LAYER
    with _LAYER_LOCK:
        _LAYER = None
