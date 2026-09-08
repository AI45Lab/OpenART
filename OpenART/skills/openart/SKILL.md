---
name: openart
description: Guide an OpenART agent or contributor through planning, running, extending, and debugging the framework.
metadata:
  scope: operator
  version: 1.0.0
  audiences: [agent, human]
---

# OpenART guide

Use this skill when a request concerns the OpenART benchmark, planner, scenario
generation, managed tools, target/attacker runs, evaluation, or framework
development. This is the single operator entry point; do not create separate
skills for each workflow. It is guidance for work on OpenART, not a
target-visible skill, attacker payload, or authorization to run commands.

## Route the request

| Intent | Read first | Typical entry point |
| --- | --- | --- |
| Understand the framework | [`docs/00_overview.md`](../../docs/00_overview.md) | Inspect the relevant component and task bundle |
| Generate a task from a scenario | [`docs/12_planner_design_implementation_usage.md`](../../docs/12_planner_design_implementation_usage.md) | `python -m framework.planner.cli ...` |
| Expand or inspect scenario seeds | [`framework/planner/scenarios.py`](../../framework/planner/scenarios.py) | `python scripts/planner.py scenarios ...` |
| Run or compare evaluations | [`docs/09_evaluation_and_outputs.md`](../../docs/09_evaluation_and_outputs.md) | `python -m framework.cli run ...` |
| Add or select a managed tool | [`docs/07_capabilities_tools_mcp.md`](../../docs/07_capabilities_tools_mcp.md) | Inspect `../openart-tools/` and `tool_use_graph.json` |
| Extend the framework | [`docs/10_extension_guides.md`](../../docs/10_extension_guides.md) | Prefer a config-driven change |
| Diagnose a failure | [`docs/11_debugging_and_testing.md`](../../docs/11_debugging_and_testing.md) | Inspect logs, prepared artifacts, and focused tests |

## Standard workflow

1. Confirm the repository root and inspect `git status` before editing.
2. Read the route-specific document and inspect existing configs/artifacts.
3. Prefer the smallest config-driven change; avoid duplicating taxonomy or
   command behavior in this skill.
4. Run a local or single-scenario smoke check before a batch or Docker launch.
5. Validate the generated task, scenario, tool selection, and safety contract.
6. Preserve the output directory, validation report, and failure artifacts.

## Planner and corpus guidance

Planner credentials, endpoint, and model belong in `.env` or the shell through
`OPENART_PLANNER_API_KEY`, `OPENART_PLANNER_BASE_URL`, and
`OPENART_PLANNER_MODEL`. Use the approved model configured by the repository
(for example `glm-5.3-flash`) rather than hard-coding a model in generated
tasks or this skill. Keep the planner tool store explicit with `--tool-store`
and keep output directories separate for independent runs.

For scenario or corpus changes, preserve the repository's scenario schema and
coverage metadata. Do not silently overwrite an existing corpus; use a new
output directory or an explicit, reviewed continuation plan.

## Tool and target boundary

Managed tool guides under `../openart-tools/` describe capabilities available
to a runtime agent. Target-native skills and attacker output are controlled by
task configuration and `vector_permissions`. Never copy this operator guide
into a target workspace, `tool_guide.md`, or an attacker-controlled surface.

## Safety and authorization

This skill explains what to inspect and which existing entry point to use. It
does not authorize Docker launches, external service calls, large paid planner
batches, destructive cleanup, repository resets, or pushes. Ask for explicit
confirmation before those actions. Keep secrets out of Markdown, logs, task
bundles, and committed configuration.
