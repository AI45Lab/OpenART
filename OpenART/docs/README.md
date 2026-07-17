# OpenART Documentation

This is the canonical OpenART documentation set. It is organized as a numbered
series so users can start with execution basics and developers can drill down
into implementation details without reading stale walkthroughs.

## Canonical Series

| File | Purpose |
|------|---------|
| [00_overview.md](00_overview.md) | What OpenART is, the core mental model, and major components |
| [01_quickstart.md](01_quickstart.md) | Installation, environment variables, Docker images, and common run commands |
| [02_runtime_architecture.md](02_runtime_architecture.md) | Orchestrator, containers, workspace layers, target-surface materialization, and run sequence |
| [03_task_and_config_model.md](03_task_and_config_model.md) | task directories, target configs, attacker configs, managed tools, evaluators, and outputs |
| [04_target_compatibility.md](04_target_compatibility.md) | `prompt_cli`, model delivery, and native surfaces |
| [05_attacker_design.md](05_attacker_design.md) | Attacker runtime, vector permissions, feedback loop, tools, and artifacts |
| [06_attack_surfaces.md](06_attack_surfaces.md) | Workspace files, target-native surfaces, task rewrite, memory/history, and permissions |
| [07_capabilities_tools_mcp.md](07_capabilities_tools_mcp.md) | Managed tool store, `tool_use_graph.json`, host env resolution, and runtime staging |
| [08_graph_rl_attacker.md](08_graph_rl_attacker.md) | Graph-RL-control attacker design, data flow, config knobs, and artifacts |
| [09_evaluation_and_outputs.md](09_evaluation_and_outputs.md) | Deterministic evaluator, LLM judge, traces, timing, and output directories |
| [10_extension_guides.md](10_extension_guides.md) | Add a target, managed tool, attacker, attack surface, evaluator, or task |
| [11_debugging_and_testing.md](11_debugging_and_testing.md) | Common failures, inspection commands, pytest targets, and artifact checklist |
| [12_planner_design_implementation_usage.md](12_planner_design_implementation_usage.md) | Scenario-first safe-world planner design, generated bundle contract, usage, extension points, and validation |
| [13_target_agent_integration_matrix.md](13_target_agent_integration_matrix.md) | Target-agent integration matrix for awesome-deepseek-agent candidates and baseline attack vectors |

## Recommended Reading Paths

For running OpenART:

```text
00_overview -> 01_quickstart -> 03_task_and_config_model
             -> 09_evaluation_and_outputs -> 11_debugging_and_testing
```

For target compatibility work:

```text
00_overview -> 02_runtime_architecture -> 04_target_compatibility
             -> 06_attack_surfaces -> 10_extension_guides
```

For attacker design work:

```text
00_overview -> 02_runtime_architecture -> 05_attacker_design
             -> 06_attack_surfaces -> 07_capabilities_tools_mcp
             -> 08_graph_rl_attacker
```

For planner generation work:

```text
00_overview -> 03_task_and_config_model -> 07_capabilities_tools_mcp
             -> 12_planner_design_implementation_usage
             -> 11_debugging_and_testing
```

## Current Runtime Truth

- Claude Code, OpenCode, Codex, Gemini, Continue CLI, and Reasonix use
  `framework: prompt_cli` for process execution.
- OpenCode and Claude Code no longer have dedicated runner classes.
- `surface_family` labels native target surfaces, while `model_integration`
  declares model binding and env/config delivery.
- Attacker compatibility is config and command based through
  `GenericCommandAttacker`.
- `vector_permissions` decides which attacker outputs the framework commits.
- `--tool-store` stages graph-selected tools when a graph exists, otherwise all
  valid live tools in the store.
- The scenario-first safe-world planner uses the OpenCode backend and validates
  generated bundles before they are treated as usable tasks.
