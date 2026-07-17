# Evaluation and Outputs

OpenART evaluators consume traces, task snapshots, service snapshots, and
rubrics. They do not need direct access to target model internals.

## Evaluator Types

| Evaluator | Source | Purpose |
|-----------|--------|---------|
| `DeterministicEvaluator` | `framework/components/evaluators.py` | Run task-specific Python rules |
| `LLMJudgeEvaluator` | `framework/components/evaluators.py` | Ask an OpenAI-compatible judge model |
| `CompositeEvaluator` | `framework/components/evaluators.py` | Run deterministic and LLM evaluators together |

Evaluator result type:

```text
EvaluatorResult
  |
  +-- run_id
  +-- decision
  +-- score
  +-- subscores
  +-- rationale
  +-- artifacts
  +-- metadata
```

## Strategy Selection

CLI option:

```bash
--eval-strategy auto|deterministic|llm|both
```

Behavior:

| Strategy | Behavior |
|----------|----------|
| `auto` | Prefer deterministic evaluator when present; use LLM when suitable |
| `deterministic` | Run only task deterministic evaluator |
| `llm` | Run only LLM judge |
| `both` | Run composite evaluator |

## Deterministic Evaluation

Task directories map:

```text
utils/evaluator.py -> deterministic evaluator
```

The deterministic evaluator runs the task's `utils/evaluator.py`. It accepts
several common evaluator entrypoint names:

```text
evaluate
evaluator
evaluate_bundle
classify
grade_checkpoints
```

The evaluator receives the values its function signature asks for. OpenART can
provide:

- run id
- trace path
- task workspace snapshot
- service snapshots
- workspace paths such as `workspace_root`, `workspace_dir`, `uploads_dir`,
  `bundle_dir`, and `index_filepath`
- optional harness modules and runtime environment values

It should return an `EvaluatorResult`, a result-like dict, a generated-safety
dict, or a checkpoint-style result. OpenART normalizes those into
`EvaluatorResult`.

## Evaluator Harness Compatibility

Some evaluators import shared helper modules such as `config`, `common`, or
`scoring`. Those helpers are not part of every task directory, so OpenART
supports a separate evaluator harness directory as an evaluator compatibility
layer.

Use the CLI option:

```bash
python -m framework.cli run \
  --task <task-dir> \
  --evaluator-harness <harness-dir>
```

or set:

```bash
export OPENART_EVAL_HARNESS=/absolute/path/to/oas_harness
```

The harness directory is expected to contain any of:

```text
config.py
common.py
scoring.py
```

Runtime behavior:

```text
host harness path
  |
  +-- mounted read-only into task container at /harness
  |
  +-- added to PYTHONPATH while deterministic evaluator runs
  |
  +-- used to satisfy evaluator imports like `import scoring`
```

When a task container is active, OpenART evaluates inside that task container
with:

```text
rules module: /task/utils/evaluator.py
harness:      /harness
workspace:    /workspace
```

When evaluating outside the container, OpenART temporarily adds the host
harness path and task root to Python import resolution.

Harness environment:

- `--evaluator-harness` wins over `OPENART_EVAL_HARNESS`
- `--harness` is a deprecated compatibility alias for older wrappers
- `OPENART_EVAL_ENV` can pass comma-separated evaluator env values, for example
  `OPENART_EVAL_ENV=FOO=bar,MODE=test`
- if a harness or external services are configured, runtime service env sets
  `OAS_EXTERNAL_MODE=real` unless already provided

The bundled compatibility harness lives at:

```text
openagentsafety_utils/oas_harness
```

It is a compatibility shim for evaluator imports. It is not target model
configuration, not a target runtime hook, and not visible to the target runner.

## LLM Judge Evaluation

Task directories map:

```text
checkpoints.md -> LLM judge rubric
```

Judge environment:

```bash
export JUDGE_BASE_URL="http://your-endpoint/v1"
export JUDGE_MODEL="your-judge-model"
export JUDGE_API_KEY="your-key"
```

The LLM judge receives a compact evaluation payload, not raw private target
state.

## Composite Evaluation

`CompositeEvaluator` runs deterministic and LLM evaluation and merges results.
Use it when deterministic checks catch concrete state changes but an LLM rubric
is needed for semantic judgment.

The merged result preserves child results in metadata.

## Target Attempts and Feedback

After each target attempt:

```text
target run
  |
  v
task snapshot + service snapshots
  |
  v
evaluator
  |
  v
EvaluatorResult
  |
  +-- pass -> finish
  +-- fail/retry -> write attacker feedback guidance
```

If the attacker supports `feedback_loop` and more iterations remain, the
orchestrator can rerun the attacker before the next target attempt.

## Trace

`trace.jsonl` records structured events:

```text
run_start
runner_start
target output events
runner_end
attacker_start
attacker_end
evaluation events
```

Trace sinks include:

```text
JsonlTraceSink
MemoryTraceSink
SqliteTraceSink
```

Most runs use JSONL.

## Timing

`timing.json` records phase and event timings. It is useful for debugging:

- Docker setup slowness
- target timeout
- attacker timeout
- evaluator latency
- target-surface materialization cost
- workspace copy overhead

## Run Directory Layout

Typical output:

```text
outputs/<run-id>/
  |
  +-- result.json
  +-- runtime.log
  +-- trace.jsonl
  +-- timing.json
  +-- task_container/
  +-- workspace/
  +-- control/
  +-- runner_outputs/
  +-- evaluator_inputs/
  +-- evaluator_outputs/
  +-- evaluation_iterations/
  +-- attacker_outputs/
```

## Workspace Outputs

```text
workspace/
  |
  +-- shared/
  |     final target-visible workspace
  |
  +-- snapshots/
  |     workspace snapshots before/after phases
  |
  +-- attacker_outputs/
        archived attacker live output by phase/iteration
```

Use `workspace/shared/` when you want to inspect what the target actually saw as
normal workspace content.

## Control Outputs

```text
control/target/
  |
  +-- base/
  +-- final/
  +-- snapshots/
  +-- materialization.json
```

Use `base/` to inspect initial target-native files and `final/` to inspect
allowed attacker changes after filtering.

`materialization.json` summarizes whether target-native files came from base or
attacker output and which paths were ignored.

## Attacker Outputs

```text
attacker_outputs/<attacker-name>/
  |
  +-- command.sh
  +-- stdout.txt
  +-- stderr.txt
  +-- status.json
  +-- result.json
  +-- prepared/
  +-- iterations/
  +-- target_control_snapshot.json
  +-- plugin artifacts copied from .openart_attacker_artifacts
```

For Graph-RL, this directory also contains graph, strategy, scratch, and
validation artifacts.

## Runner Outputs

```text
runner_outputs/target/
  |
  +-- command.sh
  +-- stdout.txt
  +-- stderr.txt
  +-- status.json
  +-- iterations/
```

Use these files to debug target CLI behavior independently of evaluator
results.

## Evaluator Inputs and Outputs

```text
evaluator_inputs/
  |
  +-- task_snapshot.json
  +-- service_snapshots.json

evaluator_outputs/
  |
  +-- <evaluator-name>/
        evaluator-specific artifacts
```

`evaluation_iterations/iter_XXX/` stores per-attempt copies for feedback and
postmortem analysis.

## Final Result

`result.json` contains the final normalized evaluator result:

```json
{
  "run_id": "...",
  "decision": "pass",
  "score": 1.0,
  "subscores": {},
  "rationale": "...",
  "artifacts": {},
  "metadata": {}
}
```

If the run fails before evaluation, the result represents the failing phase,
such as attacker or target execution failure.

## Interpreting Failure

Start with:

```text
result.json
runtime.log
attacker_outputs/*/status.json
runner_outputs/target/status.json
evaluator_outputs/
timing.json
```

Then decide which phase failed:

| Symptom | Likely area |
|---------|-------------|
| attacker exit code nonzero | attacker script, env, image, timeout |
| target exit code nonzero | target config, model env, CLI, image |
| evaluator says fail | scenario behavior, state mismatch, rubric |
| missing control files | vector permissions or provider surface mismatch |
