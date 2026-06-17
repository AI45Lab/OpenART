# Runtime Architecture

This document describes the live execution path: how the CLI becomes an
orchestrator, how containers are mounted, how attacker output is filtered, and
how evaluator feedback can drive another iteration.

## Component Graph

```text
framework.cli.commands
  |
  +-- load TaskBundleSpec
  +-- load target config
  +-- load managed tool store, if configured
  |
  v
OrchestratorFactory
  |
  +-- TaskContainer
  +-- RunnerContainer + PromptCLIRunner
  +-- optional attacker RunnerContainer + GenericCommandAttacker
  +-- ControlPlaneManager
  +-- Evaluator
  |
  v
Orchestrator
  |
  +-- setup
  +-- attacker phase
  +-- target attempts
  +-- evaluator
  +-- feedback retry
  +-- teardown
```

The factory builds objects. The orchestrator decides execution order.

## Setup Sequence

At setup time the orchestrator:

```text
1. builds/creates/starts the task container
2. seeds the shared workspace
3. snapshots the prepared workspace
4. builds the target-surface base bundle
5. writes workspace flow metadata
```

The target runner is prepared later, after the optional `before_target` attacker
has had a chance to modify allowed workspace and target-native files.

## Container Roles

| Container | Working path | Purpose |
|-----------|--------------|---------|
| task container | `/workspace` | Owns task environment and shared workspace |
| target runner container | `/workspace` | Runs the target agent CLI against shared workspace |
| attacker container | `/workspace` | Runs attacker script against input snapshots and output scratch |

The task container is the source of final workspace snapshots. Runner containers
are helper containers used to execute target or attacker commands.

## Workspace Layers

```text
task seed directory
  |
  v
workspace/shared/
  |
  +-- copied to attacker input snapshot
  |
  +-- copied to attacker output scratch
  |
  +-- mounted into target runner
```

The attacker sees:

| Container path | Access | Meaning |
|----------------|--------|---------|
| `/workspace/.openart_input_workspace` | read-only | shared workspace snapshot before attacker run |
| `/workspace` | read-write | attacker output scratch |
| `/workspace/.openart_feedback` | read-only | feedback, trace, evaluator, prior attacker outputs |
| `/workspace/.openart_target_control_input` | read-only | base target-native surface bundle |
| `/workspace/.openart_target_control_output` | read-write | proposed target-native surface bundle |

After the attacker exits successfully, OpenART compares scratch output to the
shared workspace. It commits normal workspace changes only when
`workspace_files` is allowed.

## Target-Surface Flow

Target-surface materialization represents files the target framework natively trusts:

```text
target config attack_surfaces
  |
  v
surface base
  |
  +-- manifest maps paths to vectors
  |
  v
attacker target-surface output
  |
  v
finalize_from_attacker_output()
  |
  +-- keep allowed vectors
  +-- ignore disallowed paths
  +-- apply replace/append semantics
  |
  v
final target-surface bundle
  |
  v
target-visible materialization
```

The target-surface channel exists only when:

- the target config has `attack_surfaces`
- the attacker sets `target_control_plane: true`

Allowed vectors are still controlled by `attacker.vector_permissions`.

## Run Sequence

```text
Orchestrator.run()
  |
  +-- prepare control base
  |
  +-- before_target attacker, if configured
  |     |
  |     +-- snapshot shared workspace
  |     +-- sync workspace/surface/feedback to attacker dirs
  |     +-- run attacker command
  |     +-- archive attacker output
  |     +-- apply allowed workspace diff
  |     +-- finalize allowed target-surface diff
  |
  +-- refresh target-surface mounts
  +-- stage task rewrite, if produced
  +-- prepare target runner
  |
  +-- target attempt 1
  +-- evaluator attempt 1
  +-- write feedback guidance
  |
  +-- optional feedback attacker and next target attempt
  |
  +-- optional after_target attacker
  |
  v
final EvaluatorResult
```

## Feedback Loop

When `attacker.feedback_loop: true` and the run has more target iterations
available, the same attacker can run again after an evaluator failure.

The retry attacker receives:

```text
attack_iteration = next attacker run number
feedback_iteration = target iteration that produced feedback
```

Feedback is exposed through:

```text
/workspace/.openart_feedback/
  |
  +-- trace.jsonl
  +-- evaluator_inputs/
  +-- evaluator_outputs/
  +-- runner_outputs/target/
  +-- evaluation_iterations/
  +-- attacker_feedback_guidance.json
  +-- attacker_outputs/<attacker-name>/
```

The attacker does not mutate evaluator artifacts directly. It reads feedback and
proposes another set of workspace/native-surface changes.

## Target Runner Preparation

Target runner preparation happens after `before_target` control materialization.
This is important because runner home overlays and target-native files
must be visible before the target CLI starts.

Runner preparation includes:

- build/create/start target runner container
- stage model config or env delivery
- install managed tool metadata and wrappers
- set `HOME` and `XDG_CONFIG_HOME`
- merge materialized home files before each target run

## Runtime ASCII Diagram

```text
+-------------+     +---------------------------+     +------------------+
| task bundle |---->| task container/workspace  |<--->| target runner    |
+-------------+     +-------------+-------------+     +--------+---------+
                                  ^                            |
                                  |                            v
                       allowed workspace/surface       target stdout/stderr
                                  |                            |
                                  v                            v
                         +--------+---------+          +-------+-------+
                         | attacker runner  |          | evaluator     |
                         +--------+---------+          +-------+-------+
                                  ^                            |
                                  |                            v
                                  +--------- feedback ---------+
```

## Key Implementation Files

| Behavior | Source |
|----------|--------|
| CLI run wiring | `framework/cli/commands.py` |
| Component construction | `framework/core/factory.py` |
| Runtime loop | `framework/core/orchestrator.py` |
| Workspace copy/diff/snapshot | `framework/core/workspace.py` |
| Target-surface filtering | `framework/core/control_plane.py` |
| Target command execution | `framework/components/runners.py` |
| Attacker command execution | `framework/attackers/methods/generic_cmd.py` |
| Evaluator logic | `framework/components/evaluators.py` |

## Debugging Runtime State

For a completed or failed run, inspect:

```text
runtime.log
timing.json
trace.jsonl
workspace/shared/
workspace/attacker_outputs/
control/target/materialization.json
attacker_outputs/<attacker-name>/status.json
attacker_outputs/<attacker-name>/command.sh
runner_outputs/target/
evaluator_outputs/
```

If target-visible files look wrong, compare:

```text
control/target/base/
control/target/final/
workspace/shared/
workspace/attacker_outputs/<attacker-name>/<phase>/iter_*/
```
