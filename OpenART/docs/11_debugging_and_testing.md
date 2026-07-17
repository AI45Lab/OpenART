# Debugging and Testing

This document lists practical commands and artifact checks for OpenART
development.

## First Questions

When a run fails, identify the failing phase:

```text
setup
attacker
control materialization
target
evaluator
teardown
```

Start with:

```bash
find outputs -maxdepth 3 -name runtime.log -print
find outputs -maxdepth 4 -name result.json -print
find outputs -maxdepth 5 -name status.json -print
```

## Runtime Logs

Inspect:

```text
runtime.log
timing.json
trace.jsonl
```

Use `timing.json` to distinguish a timeout from a fast command failure.

## Attacker Debugging

Inspect:

```text
attacker_outputs/<attacker-name>/command.sh
attacker_outputs/<attacker-name>/stdout.txt
attacker_outputs/<attacker-name>/stderr.txt
attacker_outputs/<attacker-name>/status.json
attacker_outputs/<attacker-name>/result.json
```

If the attacker succeeded but had no effect, inspect:

```text
allowed_control_vectors
workspace_vector_enabled
ignored_workspace_paths
ignored_target_control_paths
target_control_diff
materialized_target_control_diff
```

inside attacker `result.json`.

## Target Debugging

Inspect:

```text
runner_outputs/target/command.sh
runner_outputs/target/stdout.txt
runner_outputs/target/stderr.txt
runner_outputs/target/status.json
workspace/shared/
```

Common target issues:

- wrong `TARGET_BASE_URL`
- wrong `TARGET_MODEL`
- missing API key
- missing Docker image
- prompt flag mismatch
- target CLI auto-update or first-run prompt
- native config rendered to wrong destination

## Target-Surface Debugging

Inspect:

```text
control/target/base/.openart-target-control-manifest.json
control/target/base/
control/target/final/
control/target/materialization.json
workspace/shared/
```

Common control issues:

- attacker did not set `target_control_plane: true`
- vector missing from `vector_permissions`
- vector not exposed by target config `attack_surfaces`
- path does not match provider allowed patterns
- HOME-relative file did not merge into runner HOME
- mounted mode expected an overlay rather than visible workspace file

## Managed Tool Debugging

Inspect:

```text
runner_outputs/target/prepared/tools.json
runner_outputs/target/prepared/tool_folders.json
runner_outputs/target/prepared/tool_guide.md
attacker_outputs/<attacker-name>/prepared/tools.json
attacker_outputs/<attacker-name>/skill_validation.json
```

Common managed tool-store issues:

- `tool_use_graph.json` references a tool name that is not in `openart-tools/`
- `tool.yaml:name` does not exactly match the tool folder name
- executable tools omit `source_files`
- script paths in `args` are not staged under the runtime tool state directory
- service-backed tool env vars are missing from the host environment
- quarantine folders are not named with the `.invalid.` marker

## Graph-RL Debugging

Inspect:

```text
attacker_outputs/graph-rl-control-attacker/attack_plan_ascii.txt
attacker_outputs/graph-rl-control-attacker/attack_graph.json
attacker_outputs/graph-rl-control-attacker/sampling_decision.json
attacker_outputs/graph-rl-control-attacker/opencode_scratch_graph.json
attacker_outputs/graph-rl-control-attacker/proposal_failure_classification.json
attacker_outputs/graph-rl-control-attacker/scratch_fallback_reason.json
```

If Graph-RL generated files but target did not see them, check OpenART
framework filtering before debugging the graph proposal itself.

## Evaluator Debugging

Inspect:

```text
evaluator_inputs/task_snapshot.json
evaluator_inputs/service_snapshots.json
evaluator_outputs/
evaluation_iterations/
result.json
OPENART_EVAL_HARNESS or --evaluator-harness path
```

If deterministic evaluation behaves unexpectedly, reproduce the evaluator
against the saved input snapshot where possible. For import errors involving
shared helper modules, verify that `--evaluator-harness` or
`OPENART_EVAL_HARNESS` points at the required harness directory. `--harness`
is only a deprecated compatibility alias for older wrappers.

If LLM judge output is unexpected, inspect the evaluator payload and rubric
artifacts rather than target stdout alone.

## Focused Test Commands

Run model and target compatibility tests:

```bash
python3 -m pytest OpenART/tests/unit/test_target_adapters.py
python3 -m pytest OpenART/tests/unit/test_runners_runtime.py
python3 -m pytest OpenART/tests/unit/test_factory_runtime.py
```

Run target-surface and attack-surface tests:

```bash
python3 -m pytest OpenART/tests/unit/test_control_plane.py
python3 -m pytest OpenART/tests/unit/test_visibility_policy.py
python3 -m pytest OpenART/tests/unit/test_workspace_runtime.py
```

Run attacker tests:

```bash
python3 -m pytest OpenART/tests/unit/test_opencode_attacker_prompt.py
python3 -m pytest OpenART/tests/unit/test_graph_rl_attacker.py
```

Run managed tool tests:

```bash
python3 -m pytest OpenART/tests/unit/test_tool_store.py
```

Run evaluator tests:

```bash
python3 -m pytest OpenART/tests/unit/test_evaluators_runtime.py
python3 -m pytest OpenART/tests/unit/models/test_evaluator.py
```

Run planner tests:

```bash
python3 -m pytest OpenART/tests/unit/test_opencode_planner.py
python3 -m pytest OpenART/tests/unit/test_safe_world_planner.py
```

## Docs Sanity Checks

After docs changes:

```bash
find OpenART/docs -maxdepth 2 -type f -name '*.md' -print | sort
rg -n 'OpenCode''Runner|ClaudeCode''Runner' OpenART/docs --glob '!**/archive/**'
rg -n 'config-opencode-config[-]only|config-claude_code-config[-]only' OpenART/docs --glob '!**/archive/**'
rg -n 'framework: open''code|framework: claude''_code' OpenART/docs --glob '!**/archive/**'
```

Expected result for the last three checks is no output from canonical docs.

## Common Fix Map

| Symptom | Check |
|---------|-------|
| target command not found | target image and `launch_cmd` |
| model auth error | `model_integration.delivery.env_names`, `model_integration.delivery.env`, and host env |
| attacker no effect | `vector_permissions` and materialization artifacts |
| missing target-native paths | target `attack_surfaces` and materialization manifest |
| managed tool did not load | task `tool_use_graph.json`, `--tool-store`, and prepared `tools.json` |
| target leaked scratch files | `visibility_policy` and target-visible leak reports |
| evaluator says fail but state looks correct | evaluator inputs and service snapshots |

## Useful Artifact Search

```bash
find outputs -name runtime.log -print
find outputs -name command.sh -print
find outputs -name stderr.txt -print
find outputs -name materialization.json -print
find outputs -name skill_validation.json -print
find outputs -name target_visible_leak_guard.json -print
```

Use artifact evidence before changing implementation code. Most OpenART failures
are config, permission, mount, or environment mismatches.
