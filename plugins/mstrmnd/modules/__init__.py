"""Built-in mstrmnd intelligence modules.

Add new modules by:
1. Implementing ``IntelligenceModule`` in this package
2. Appending an instance to ``BUILTIN_MODULES``

External / experimental modules can also be attached at runtime via
``IntelligenceLayer.register_module(...)``.
"""

from __future__ import annotations

from typing import List

from .alignment import AlignmentModule
from .base import IntelligenceModule, ModuleContext, ToolGate
from .policy import PolicyModule
from .vision import VisionModule
from .workspace import WorkspaceModule

BUILTIN_MODULES: List[IntelligenceModule] = [
    VisionModule(),
    AlignmentModule(),
    WorkspaceModule(),
    PolicyModule(),
]

__all__ = [
    "AlignmentModule",
    "BUILTIN_MODULES",
    "IntelligenceModule",
    "ModuleContext",
    "PolicyModule",
    "ToolGate",
    "VisionModule",
    "WorkspaceModule",
]
