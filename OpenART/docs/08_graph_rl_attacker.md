# Graph-RL-Control Attacker

The Graph-RL-control attacker is the most complex built-in attacker. It builds
or samples a structured attack graph, materializes selected actions into
workspace and target-native outputs, and records detailed artifacts for audit.

Config:

```text
configs/attacker-configs/graph-rl-control/config.yaml
```

Main script:

```text
configs/attacker-configs/graph-rl-control/run_graph_rl_attacker.py
```

## High-Level Flow

```text
read task, target instruction, attacker instruction, feedback, manifest
  |
  v
build context snapshot
  |
  v
curate strategy pool
  |
  v
propose or derive attack graph
  |
  v
validate and repair graph
  |
  v
sample Markov hypergraph path
  |
  v
materialize selected actions
  |
  +-- workspace files
  +-- target-native files
  +-- task rewrite, if enabled
  |
  v
write artifacts
```

The framework still applies normal OpenART filters after the script exits:

- `workspace_files` controls normal workspace diff commit
- target-native vectors control native file materialization
- unsupported vectors are ignored by `attack_surfaces` filtering

## Config Contract

The default config:

```yaml
attacker:
  name: graph-rl-control-attacker
  phase: before_target
  image: openart/opencode:latest
  cmd: python3
  timeout_seconds: 7800
  target_control_plane: true
  feedback_loop: true
```

It passes all important framework paths through placeholders:

```text
--target-instruction
--attacker-instruction
--input-workspace
--output-workspace
--input-target-control
--output-target-control
--feedback-dir
--attacker-history-dir
--attack-iteration
--feedback-iteration
--run-id
```

## Vector Permissions

The default Graph-RL config is broad:

```text
workspace_files
agents_md
claude_md
claude_local_md
claude_rule
claude_command
claude_skill
opencode_skill
opencode_command
agents_skill
conversation_history
auto_memory
task_rewrite
```

This does not mean every target accepts every vector. The target config's
`attack_surfaces` decides which vectors are actually available. For
model/config delivery, current benchmark targets use managed target integration
instead of exposing `model_config` as an attacker vector.

## Strategy Pool

Graph-RL maintains a strategy pool so attack planning can reuse higher-level
strategy families across runs.

Relevant artifacts and state:

```text
strategy_pool.json
strategy_candidates.json
strategy_proposal_prompt.txt
strategy_proposal_stdout.txt
strategy_critique_prompt.txt
strategy_critique_stdout.txt
```

The default visibility policy excludes these files from target-visible state.

## Scratch Realization

The script can ask OpenCode to realize a candidate attack in a scratch workspace
before turning it into a graph. Scratch/state roots are kept outside the
target-visible workspace.

Important artifacts:

```text
opencode_scratch_graph.json
opencode_scratch_change_mappings.json
opencode_scratch_mapping_warnings.json
opencode_scratch_mapping_error.json
opencode_scratch_empty.json
opencode_scratch_skill_validation.json
```

If scratch realization fails for a transient reason, fallback paths can try a
compact retry, direct goal/action bundle realization, or previous graph reuse.

## Validation and Repair

The script validates graph structure and can perform bounded repairs.

Common artifacts:

```text
plan_shell_validation_error.json
reproposal_validation_error.json
scratch_fallback_reason.json
scratch_fallback_graph.json
context_leak_diagnostics.json
naturalness_diagnostics.json
target_recognition_diagnostics.json
```

Skill vectors can be validated by script logic before materialization. Rejected
scratch skills can be repaired before materialization.

## Sampling

The attack graph can include hyperedges. Sampling chooses a concrete path:

```text
attack graph
  |
  +-- sub_tasks
  +-- goals
  +-- actions
  +-- hyper_edges
  |
  v
sampled graph
```

Sampling artifacts:

```text
sampling_decision.json
plan_shell_sampling_trace.json
sampled_plan_shell.json
attack_plan.json
attack_graph.json
attack_plan_ascii.txt
attack_plan.mmd
```

## Materialization

Materialization writes selected graph actions into:

```text
{{output_workspace_dir}}
{{output_target_control_dir}}
```

The attacker script decides what to write. The framework later decides what to
commit.

## Important Environment Knobs

| Env var | Default in config | Meaning |
|---------|-------------------|---------|
| `OPENART_GRAPH_RL_PROMPT_TIMEOUT_SECONDS` | `7200` | Timeout for LLM prompt subprocesses |
| `OPENART_GRAPH_RL_MAX_SUB_TASKS` | `4` | Upper bound on sampled/planned subtasks |
| `OPENART_GRAPH_RL_REWARD_MODE` | `strict` | Reward/scoring mode |
| `OPENART_GRAPH_RL_COMPLETION_GAP_REPAIR` | `1` | Enable completion-gap repair |
| `OPENART_GRAPH_RL_DETECTION_ANALYSIS` | `1` | Enable detection/naturalness analysis |
| `OPENART_GRAPH_RL_VALIDATION_RETRIES` | `5` | Graph validation repair retries |
| `OPENART_GRAPH_RL_SCRATCH_RETRIES` | `3` | Scratch realization retries |
| `OPENART_GRAPH_RL_SCRATCH_FALLBACK` | `1` | Enable fallback after scratch failure |
| `OPENART_GRAPH_RL_REUSE_PREVIOUS_ON_TRANSIENT` | `1` | Reuse prior valid graph on transient failures |
| `OPENART_GRAPH_RL_OPENCODE_TOOLS` | `read,write,bash` | Tools exposed to the scratch OpenCode run |
| `OPENART_GRAPH_RL_TEMPERATURE` | script default | Sampling temperature |
| `OPENART_GRAPH_RL_MAX_STEPS` | script default | Maximum sampling steps |
| `OPENART_GRAPH_RL_SEED` | unset | Deterministic sampling seed |
| `OPENART_GRAPH_RL_STRATEGY_POOL_DIR` | state-derived | Strategy pool location |

## Visibility Policy

The config excludes scratch and planning files from target visibility:

```text
_opencode_scratch/**
.tmp_*/**
context_snapshot.json
plan_proposal_prompt.txt
opencode_scratch_prompt.txt
scratch_manifest.json
feedback_directives.json
detection_analysis_iter_*.json
strategy_*.txt
strategy_pool.json
```

This keeps attacker planning artifacts from becoming accidental target-visible
evidence.

## Debugging Graph-RL Runs

Start with:

```text
attacker_outputs/graph-rl-control-attacker/status.json
attacker_outputs/graph-rl-control-attacker/stdout.txt
attacker_outputs/graph-rl-control-attacker/stderr.txt
attacker_outputs/graph-rl-control-attacker/attack_plan_ascii.txt
attacker_outputs/graph-rl-control-attacker/attack_graph.json
```

Then compare materialized output:

```text
workspace/attacker_outputs/graph-rl-control-attacker/
control/target/final/
workspace/shared/
control/target/materialization.json
```

Common failure causes:

- OpenCode scratch timeout
- no target-visible changes after mapping
- generated skill wrapper validation failed
- graph validation errors exceeded retry limit
- vector listed by Graph-RL is not exposed by target `attack_surfaces`
- scratch artifacts leaked into target-visible output and were filtered
