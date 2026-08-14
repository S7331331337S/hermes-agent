"""Tests for the mstrmnd intelligence-layer plugin.

Covers ``plugins/mstrmnd/``:

  * config deep-merge (profile → workspace)
  * store scaffolding under HERMES_HOME / .mstrmnd
  * IntelligenceLayer context injection + inject_mode
  * policy block gates
  * slash command status / init / show
  * bundled-plugin discovery when enabled
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest
import yaml


@pytest.fixture(autouse=True)
def _isolate_env(tmp_path, monkeypatch):
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    # Keep cwd inside the temp tree so a developer's repo-local ``.mstrmnd/``
    # overlay cannot leak into profile-only tests (lists/keys replace on merge).
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.delenv("MSTRMND_DISABLE", raising=False)
    # Reset singleton between tests
    mod = _load_plugin_package()
    mod.reset_layer_for_tests()
    yield hermes_home
    mod.reset_layer_for_tests()


def _repo_plugin_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "plugins" / "mstrmnd"


def _load_plugin_package():
    """Import plugins/mstrmnd as hermes_plugins.mstrmnd with submodules."""
    plugin_dir = _repo_plugin_dir()
    if "hermes_plugins" not in sys.modules:
        ns = types.ModuleType("hermes_plugins")
        ns.__path__ = []
        sys.modules["hermes_plugins"] = ns

    # Drop cached modules so HERMES_HOME changes take effect cleanly.
    for key in list(sys.modules):
        if key == "hermes_plugins.mstrmnd" or key.startswith("hermes_plugins.mstrmnd."):
            del sys.modules[key]

    pkg_name = "hermes_plugins.mstrmnd"
    spec = importlib.util.spec_from_file_location(
        pkg_name,
        plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = pkg_name
    mod.__path__ = [str(plugin_dir)]
    sys.modules[pkg_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Store + config
# ---------------------------------------------------------------------------


class TestStoreAndConfig:
    def test_ensure_profile_scaffold_writes_templates(self, _isolate_env):
        mod = _load_plugin_package()
        from hermes_plugins.mstrmnd.store import ensure_profile_scaffold, hermes_mstrmnd_dir

        written = ensure_profile_scaffold()
        assert written
        root = hermes_mstrmnd_dir()
        assert (root / "vision.yaml").is_file()
        assert (root / "alignment.yaml").is_file()
        assert (root / "workspace.yaml").is_file()
        # Second call is a no-op without force
        assert ensure_profile_scaffold() == []

    def test_workspace_overlay_merges_over_profile(self, _isolate_env, tmp_path, monkeypatch):
        mod = _load_plugin_package()
        from hermes_plugins.mstrmnd.config_loader import load_merged_config
        from hermes_plugins.mstrmnd.store import hermes_mstrmnd_dir

        _write_yaml(
            hermes_mstrmnd_dir() / "vision.yaml",
            {"name": "profile", "principles": ["a"], "tagline": "base"},
        )
        ws = tmp_path / "project"
        ws.mkdir()
        monkeypatch.chdir(ws)
        _write_yaml(
            ws / ".mstrmnd" / "vision.yaml",
            {"name": "workspace", "principles": ["b"]},
        )
        merged = load_merged_config("vision.yaml", cwd=str(ws))
        assert merged["name"] == "workspace"
        assert merged["principles"] == ["b"]  # list replace, not concat
        assert merged["tagline"] == "base"  # inherited


# ---------------------------------------------------------------------------
# Layer behaviour
# ---------------------------------------------------------------------------


class TestIntelligenceLayer:
    def test_pre_llm_context_first_turn(self, _isolate_env, tmp_path, monkeypatch):
        mod = _load_plugin_package()
        from hermes_plugins.mstrmnd.layer import get_layer
        from hermes_plugins.mstrmnd.store import ensure_profile_scaffold

        ensure_profile_scaffold()
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.chdir(ws)
        (ws / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
        _write_yaml(
            ws / ".mstrmnd" / "workspace.yaml",
            {
                "label": "demo",
                "focus": ["ship the layer"],
                "context_paths": ["AGENTS.md", "MISSING.md"],
            },
        )

        layer = get_layer()
        layer.reload(cwd=str(ws))
        result = layer.build_pre_llm_context(
            session_id="s1",
            is_first_turn=True,
            user_message="hello",
        )
        assert result and "context" in result
        ctx = result["context"]
        assert "mstrmnd intelligence layer" in ctx
        assert "[mstrmnd:vision]" in ctx
        assert "[mstrmnd:alignment]" in ctx
        assert "[mstrmnd:workspace]" in ctx
        assert "Workspace: demo" in ctx
        assert "AGENTS.md" in ctx
        assert "MISSING.md" in ctx

        # first_turn mode: second call in same session should skip
        again = layer.build_pre_llm_context(
            session_id="s1",
            is_first_turn=False,
            user_message="again",
        )
        assert again is None

    def test_inject_mode_every_turn(self, _isolate_env):
        mod = _load_plugin_package()
        from hermes_plugins.mstrmnd.layer import get_layer
        from hermes_plugins.mstrmnd.store import hermes_mstrmnd_dir

        _write_yaml(
            hermes_mstrmnd_dir() / "alignment.yaml",
            {"inject_mode": "every_turn", "guidance": ["stay aligned"]},
        )
        _write_yaml(
            hermes_mstrmnd_dir() / "vision.yaml",
            {"name": "x", "principles": ["p"]},
        )
        layer = get_layer()
        layer.reload()
        a = layer.build_pre_llm_context(session_id="s", is_first_turn=True)
        b = layer.build_pre_llm_context(session_id="s", is_first_turn=False)
        assert a and b

    def test_vision_flattens_mapping_principles(self, _isolate_env):
        """Unquoted ``key: value`` YAML list items become dicts — flatten them."""
        mod = _load_plugin_package()
        from hermes_plugins.mstrmnd.layer import get_layer
        from hermes_plugins.mstrmnd.store import hermes_mstrmnd_dir

        _write_yaml(
            hermes_mstrmnd_dir() / "vision.yaml",
            {
                "name": "x",
                "principles": [
                    "plain",
                    {"Fail open": "never block unless gated"},
                ],
            },
        )
        layer = get_layer()
        layer.reload()
        ctx = layer.build_pre_llm_context(session_id="s", is_first_turn=True)
        assert ctx and "Fail open: never block unless gated" in ctx["context"]
        assert "{'Fail open'" not in ctx["context"]

    def test_disable_env(self, _isolate_env, monkeypatch):
        mod = _load_plugin_package()
        from hermes_plugins.mstrmnd.layer import get_layer
        from hermes_plugins.mstrmnd.store import ensure_profile_scaffold

        ensure_profile_scaffold()
        monkeypatch.setenv("MSTRMND_DISABLE", "1")
        layer = get_layer()
        layer.reload()
        assert layer.build_pre_llm_context(session_id="s", is_first_turn=True) is None

    def test_policy_blocks_matching_terminal(self, _isolate_env):
        mod = _load_plugin_package()
        from hermes_plugins.mstrmnd.layer import get_layer
        from hermes_plugins.mstrmnd.store import hermes_mstrmnd_dir

        _write_yaml(
            hermes_mstrmnd_dir() / "alignment.yaml",
            {
                "guidance": [],
                "policies": [
                    {
                        "id": "no-force-push",
                        "tools": ["terminal"],
                        "match": "git push --force",
                        "action": "block",
                        "message": "nope",
                    }
                ],
            },
        )
        layer = get_layer()
        layer.reload()
        blocked = layer.gate_tool(
            "terminal",
            {"command": "git push --force origin main"},
            session_id="s",
        )
        assert blocked == {"action": "block", "message": "nope"}

        allowed = layer.gate_tool(
            "terminal",
            {"command": "git status"},
            session_id="s",
        )
        assert allowed is None


# ---------------------------------------------------------------------------
# Slash + register
# ---------------------------------------------------------------------------


class TestSlashAndRegister:
    def test_slash_status_and_init(self, _isolate_env, tmp_path, monkeypatch):
        mod = _load_plugin_package()
        out = mod._handle_slash("init")
        assert "Seeded" in out or "already present" in out
        status = mod._handle_slash("status")
        assert "mstrmnd intelligence layer" in status
        assert "vision" in status

        ws = tmp_path / "proj"
        ws.mkdir()
        monkeypatch.chdir(ws)
        mod.reset_layer_for_tests()
        out_ws = mod._handle_slash("init --workspace")
        assert (ws / ".mstrmnd" / "vision.yaml").is_file()
        assert "workspace" in out_ws.lower() or ".mstrmnd" in out_ws

    def test_slash_show_vision(self, _isolate_env):
        mod = _load_plugin_package()
        mod._handle_slash("init")
        shown = mod._handle_slash("show vision")
        assert "mstrmnd vision" in shown
        # JSON body present
        assert '"name"' in shown or "name" in shown

    def test_register_wires_hooks_and_commands(self, _isolate_env):
        mod = _load_plugin_package()

        class FakeCtx:
            def __init__(self):
                self.hooks = []
                self.commands = []
                self.cli = []

            def register_hook(self, name, cb):
                self.hooks.append(name)

            def register_command(self, name, handler, description="", args_hint=""):
                self.commands.append(name)

            def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
                self.cli.append(name)

        ctx = FakeCtx()
        mod.register(ctx)
        assert "pre_llm_call" in ctx.hooks
        assert "pre_tool_call" in ctx.hooks
        assert "on_session_start" in ctx.hooks
        assert "mstrmnd" in ctx.commands
        assert "mstrmnd" in ctx.cli


class TestDiscovery:
    def _write_enabled_config(self, hermes_home, names):
        cfg_path = hermes_home / "config.yaml"
        cfg_path.write_text(yaml.safe_dump({"plugins": {"enabled": list(names)}}))

    def test_mstrmnd_discovered_but_not_loaded_by_default(self, _isolate_env):
        from hermes_cli import plugins as pmod

        mgr = pmod.PluginManager()
        mgr.discover_and_load()
        assert "mstrmnd" in mgr._plugins
        loaded = mgr._plugins["mstrmnd"]
        assert loaded.manifest.source == "bundled"
        assert not loaded.enabled
        assert loaded.error and "not enabled" in loaded.error

    def test_mstrmnd_loads_when_enabled(self, _isolate_env):
        self._write_enabled_config(_isolate_env, ["mstrmnd"])
        from hermes_cli import plugins as pmod

        mgr = pmod.PluginManager()
        mgr.discover_and_load()
        loaded = mgr._plugins["mstrmnd"]
        assert loaded.enabled
        assert "pre_llm_call" in loaded.hooks_registered
        assert "pre_tool_call" in loaded.hooks_registered
        assert "on_session_start" in loaded.hooks_registered
        assert "mstrmnd" in loaded.commands_registered
