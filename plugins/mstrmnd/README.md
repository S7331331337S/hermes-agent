# mstrmnd

Intelligence layer between the Hermes **harness** (CLI / gateway / TUI / ACP)
and the **operator** (`AIAgent`). Provides a scalable framework for:

- **Vision** — design intent and north-star principles
- **Alignment** — soft behavioral guidance + optional hard tool policies
- **Workspace config** — project-local focus, prefer/avoid, context pointers

Implemented as a bundled Hermes plugin. No core patches. Context is injected
into the **user message** via `pre_llm_call` so the system-prompt cache stays
intact.

## Enable

```bash
hermes plugins enable mstrmnd
hermes mstrmnd init              # seed $HERMES_HOME/mstrmnd/*.yaml
hermes mstrmnd init --workspace  # also seed ./.mstrmnd/*.yaml
```

Temporary kill switch: `MSTRMND_DISABLE=1`.

## Architecture

```
CLI / Gateway / TUI / ACP          ← harness
        │
        ▼
   AIAgent conversation loop       ← operator
        │
        ├── pre_llm_call  ← mstrmnd modules compose ephemeral context
        ├── pre_tool_call ← optional policy gates
        └── session start/end lifecycle
              ▲
              │  plugins/mstrmnd (this plugin)
```

### Modules (extensible)

| Module | Priority | Role |
|---|---|---|
| `vision` | 10 | Name, tagline, principles, north star |
| `alignment` | 20 | Soft guidance bullets |
| `workspace` | 30 | Label, focus, prefer/avoid, context path presence |
| `policy` | 40 | Optional `pre_tool_call` block rules from `alignment.policies` |

Add a module by implementing `IntelligenceModule` in `modules/` and appending
it to `BUILTIN_MODULES`, or call `get_layer().register_module(...)` at runtime.

## Config layout

Merge order (later wins; lists replace):

1. `$HERMES_HOME/mstrmnd/<file>.yaml` — profile defaults
2. `./.mstrmnd/<file>.yaml` (or `./.hermes/mstrmnd/`) — workspace overlay

Files: `vision.yaml`, `alignment.yaml`, `workspace.yaml`.

`alignment.inject_mode`:

| Value | Behaviour |
|---|---|
| `first_turn` (default) | Inject once per session |
| `every_turn` | Inject on every operator turn |
| `never` | Context off; policy gates still apply |

### Example block policy

```yaml
# alignment.yaml
policies:
  - id: no-force-push
    tools: [terminal]
    match: "git push --force"
    action: block
    message: "Force-push is blocked by mstrmnd alignment policy."
```

## Surfaces

```
/mstrmnd status
/mstrmnd init [--workspace] [--force]
/mstrmnd reload
/mstrmnd show vision|alignment|workspace

hermes mstrmnd status
hermes mstrmnd init [--workspace] [--force]
hermes mstrmnd reload
```

## Design constraints (deliberate)

- **Fail open** — module errors never abort the operator loop
- **Cache-safe** — never mutate the system prompt
- **Plugin-only** — does not patch `run_agent.py` / `cli.py` / `gateway/run.py`
- **Profile-aware** — all state under `get_hermes_home()/mstrmnd`
- **Complementary** — does not replace `AGENTS.md` / `SOUL.md`; surfaces whether declared context files exist

## Growth path

1. Seed vision + alignment for a profile
2. Add per-repo `.mstrmnd/` overlays as workspaces diverge
3. Drop new modules for scoring, routing hints, or domain gates
4. Optionally wire `ctx.llm` side-calls inside a module for adaptive alignment
   (keep fail-open; keep injections short)
