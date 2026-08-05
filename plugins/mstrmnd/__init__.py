"""mstrmnd — intelligence layer between the Hermes harness and the operator.

Sits on Hermes plugin hooks (no core patches):

* ``on_session_start`` / ``on_session_end`` — lifecycle + profile scaffold
* ``pre_llm_call`` — inject vision / alignment / workspace context into the
  *user message* (cache-safe; never mutates the system prompt)
* ``pre_tool_call`` — optional hard policy gates from ``alignment.yaml``

Operator surfaces:

* Slash: ``/mstrmnd status|init|reload|show <section>``
* CLI: ``hermes mstrmnd status|init|reload``

Enable with::

    hermes plugins enable mstrmnd

Disable temporarily with ``MSTRMND_DISABLE=1``.
"""

from __future__ import annotations

import argparse
import logging
import textwrap
from typing import Any, Optional

from .layer import get_layer, reset_layer_for_tests
from .store import (
    CONFIG_NAMES,
    ensure_profile_scaffold,
    ensure_workspace_scaffold,
    hermes_mstrmnd_dir,
)

logger = logging.getLogger(__name__)

__all__ = ["register", "get_layer", "reset_layer_for_tests"]


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


def _on_session_start(**kwargs: Any) -> None:
    try:
        get_layer().on_session_start(**kwargs)
    except Exception as exc:
        logger.warning("mstrmnd on_session_start failed: %s", exc)


def _on_session_end(**kwargs: Any) -> None:
    try:
        get_layer().on_session_end(**kwargs)
    except Exception as exc:
        logger.warning("mstrmnd on_session_end failed: %s", exc)


def _on_pre_llm_call(**kwargs: Any) -> Optional[dict]:
    try:
        return get_layer().build_pre_llm_context(**kwargs)
    except Exception as exc:
        logger.warning("mstrmnd pre_llm_call failed: %s", exc)
        return None


def _on_pre_tool_call(tool_name: str = "", args: Any = None, **kwargs: Any) -> Optional[dict]:
    try:
        return get_layer().gate_tool(tool_name, args, **kwargs)
    except Exception as exc:
        logger.warning("mstrmnd pre_tool_call failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Slash command
# ---------------------------------------------------------------------------

_HELP = textwrap.dedent(
    """\
    /mstrmnd — intelligence layer (vision · alignment · workspace)

    status                 Show layer + module status
    init [--workspace]     Seed profile (and optional workspace) templates
    reload                 Reload YAML configs from disk
    show <section>         Print merged vision|alignment|workspace config keys
    """
).strip()


def _format_status() -> str:
    st = get_layer().status()
    lines = [
        "mstrmnd intelligence layer",
        f"  enabled:       {st['enabled']}",
        f"  inject_mode:   {st['inject_mode']}",
        f"  profile_dir:   {st['profile_dir']}",
        f"  workspace_dir: {st['workspace_dir'] or '(none — run /mstrmnd init --workspace)'}",
        f"  cwd:           {st['cwd']}",
        "  modules:",
    ]
    for mod in st["modules"]:
        flag = "on" if mod.get("enabled", True) else "off"
        extra = []
        for key in ("principle_count", "guidance_count", "focus_count", "block_policies"):
            if key in mod:
                extra.append(f"{key}={mod[key]}")
        suffix = f" ({', '.join(extra)})" if extra else ""
        lines.append(f"    - {mod['name']} [{flag}] prio={mod.get('priority')}{suffix}")
    return "\n".join(lines)


def _handle_slash(raw_args: str) -> str:
    argv = (raw_args or "").strip().split()
    if not argv or argv[0] in {"help", "-h", "--help"}:
        return _HELP

    sub = argv[0].lower()
    layer = get_layer()

    if sub == "status":
        return _format_status()

    if sub == "reload":
        layer.reload()
        return "mstrmnd: reloaded vision / alignment / workspace configs.\n" + _format_status()

    if sub == "init":
        force = "--force" in argv
        want_ws = "--workspace" in argv or "-w" in argv
        written = ensure_profile_scaffold(force=force)
        parts = []
        if written:
            parts.append(
                "Seeded profile templates:\n"
                + "\n".join(f"  - {p}" for p in written)
            )
        else:
            parts.append(f"Profile templates already present in {hermes_mstrmnd_dir()}")
        if want_ws:
            dest, ws_written = ensure_workspace_scaffold(force=force)
            if ws_written:
                parts.append(
                    f"Seeded workspace overlays in {dest}:\n"
                    + "\n".join(f"  - {p}" for p in ws_written)
                )
            else:
                parts.append(f"Workspace overlays already present in {dest}")
        layer.reload()
        return "\n".join(parts)

    if sub == "show":
        if len(argv) < 2:
            return "Usage: /mstrmnd show <vision|alignment|workspace>"
        section = argv[1].lower().strip()
        name = f"{section}.yaml"
        if name not in CONFIG_NAMES:
            return f"Unknown section '{section}'. Choose: vision, alignment, workspace"
        layer.ensure_loaded()
        from .config_loader import load_merged_config
        import json

        merged = load_merged_config(name)
        if not merged:
            return f"No {section} config loaded yet. Try `/mstrmnd init`."
        return f"mstrmnd {section} (merged):\n{json.dumps(merged, indent=2, ensure_ascii=False)}"

    return f"Unknown subcommand: {sub}\n\n{_HELP}"


# ---------------------------------------------------------------------------
# CLI: hermes mstrmnd ...
# ---------------------------------------------------------------------------


def _setup_cli(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="mstrmnd_cmd")

    sub.add_parser("status", help="Show intelligence layer status")

    p_init = sub.add_parser("init", help="Seed default mstrmnd YAML templates")
    p_init.add_argument(
        "--workspace",
        "-w",
        action="store_true",
        help="Also create .mstrmnd/ overlays in the current workspace",
    )
    p_init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing template files",
    )

    sub.add_parser("reload", help="Reload configs (useful after edits)")


def _cli_handler(args: argparse.Namespace) -> int:
    cmd = getattr(args, "mstrmnd_cmd", None) or "status"
    layer = get_layer()

    if cmd == "status":
        print(_format_status())
        return 0

    if cmd == "reload":
        layer.reload()
        print("mstrmnd: reloaded.")
        print(_format_status())
        return 0

    if cmd == "init":
        written = ensure_profile_scaffold(force=bool(getattr(args, "force", False)))
        if written:
            print("Seeded profile templates:")
            for p in written:
                print(f"  - {p}")
        else:
            print(f"Profile templates already present in {hermes_mstrmnd_dir()}")
        if getattr(args, "workspace", False):
            dest, ws_written = ensure_workspace_scaffold(
                force=bool(getattr(args, "force", False))
            )
            if ws_written:
                print(f"Seeded workspace overlays in {dest}:")
                for p in ws_written:
                    print(f"  - {p}")
            else:
                print(f"Workspace overlays already present in {dest}")
        layer.reload()
        return 0

    print(_format_status())
    return 0


# ---------------------------------------------------------------------------
# Plugin entry
# ---------------------------------------------------------------------------


def register(ctx) -> None:
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_command(
        "mstrmnd",
        handler=_handle_slash,
        description="Intelligence layer: vision, alignment, workspace config.",
        args_hint="[status|init|reload|show]",
    )
    ctx.register_cli_command(
        name="mstrmnd",
        help="mstrmnd intelligence layer (vision / alignment / workspace)",
        setup_fn=_setup_cli,
        handler_fn=_cli_handler,
        description=(
            "Framework between the Hermes harness and the operator for "
            "agent alignment and workspace config. "
            "See: hermes mstrmnd status"
        ),
    )
