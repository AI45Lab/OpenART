# Scenario-First Safe-World Planner

The planner generates OpenART task bundles from short scenario
descriptions. It first asks the planner model to write an abstract
`scenario_model.json`, then generates the complete task bundle, validates the
bundle, and repairs failed attempts before the output is treated as usable.

The planner currently uses the OpenCode backend. Use the existing module
entrypoint from `OpenART/`; no additional CLI installation is required.

## What It Produces

An accepted generated bundle contains a benign `task.md`, a target-visible
`workspace/`, a `tool_use_graph.json`, a `safety_contract.json`, an OpenART
tool manifest, deterministic evaluator files, and planner diagnostics under
`planner_artifacts/`.

The target-visible task should not expose hidden protected markers, evaluator
logic, or scoring details. Unsafe behavior is defined by the hidden contract
and evaluator.

## Inputs

Checked-in scenario seeds live in:

```text
configs/planner/scenarios/
```

Large generated seed corpora are local artifacts. They are intentionally
ignored by git and should be regenerated when needed rather than committed.

Managed tools come from the explicit `--tool-store` path, normally the sibling
`../openart-tools` directory. The planner refreshes that store, builds a
compact tool pool, and writes the final runtime manifest into the generated
bundle.

## Build Planner Image

```bash
docker build -t openart/safe-world-planner:latest \
  -f images/Dockerfile.safe-world-planner .
```

Set planner model credentials in `.env` or in the shell:

```bash
OPENART_PLANNER_BASE_URL=https://api.example.com/v1
OPENART_PLANNER_MODEL=your-planner-model
OPENART_PLANNER_API_KEY=your-planner-key
```

## Generate One Task

```bash
python -m framework.planner.cli \
  --planner-backend opencode \
  --scenario-file configs/planner/scenarios/financial-expense-brief.txt \
  --tool-store ../openart-tools \
  --tool-count 3 \
  --complexity-profile stress \
  --planner-max-repairs 2 \
  --task-id financial-expense-brief \
  --output-dir outputs/financial-expense-brief \
  --overwrite
```

Run the generated task with deterministic evaluation:

```bash
python -m framework.cli run \
  --task outputs/financial-expense-brief \
  --tool-store ../openart-tools \
  --eval-strategy deterministic \
  --output-dir outputs/financial-expense-brief-run
```

## Complexity Profiles

Built-in profiles live in `framework/planner/complexity.py`.

| Profile | Shape |
|---------|-------|
| `basic` | Small bundle with a short workflow and simple workspace |
| `rich` | Deeper workflow with more files, branches, and formats |
| `stress` | Larger workflow with stronger depth, breadth, and evaluator checks |

Use `--complexity-config` with a YAML or JSON file to override profile fields
such as workflow node ranges, dependency depth, parallel branches, external
tool-call floors, approved files, risky files, and required formats.

## Scenario Corpus Utilities

The helper module can generate local scenario files:

```bash
python -m framework.planner.scenarios \
  --diverse-count 1000 \
  --output-dir configs/planner/scenarios/generated_local_1000
```

Generated folders matching `configs/planner/scenarios/generated*/` are ignored
by git.

## Validation

The planner validates the abstract scenario contract, tool grounding, workflow
graph, workspace structure, hidden markers, and evaluator behavior. Failed
scenario or bundle generations are repaired up to `--planner-max-repairs`.

The main implementation files are:

| Area | Files |
|------|-------|
| CLI orchestration | `framework/planner/cli.py` |
| OpenCode backend | `framework/planner/opencode_backend.py` |
| Tool pool and built-ins | `framework/planner/safe_world.py` |
| Complexity profiles | `framework/planner/complexity.py` |
| Registry materialization | `framework/planner/registry.py` |
| Validation | `framework/planner/validation.py` |
| Human-facing helper | `scripts/planner.py` |
