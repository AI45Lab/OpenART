# OpenART

OpenART is a Docker-native framework for running controlled safety evaluations
against tool-using code agents. This release checkout keeps a runnable runtime,
a small set of bundled high-complexity OpenART task examples, and the managed
tool subset required by those examples.

This repository intentionally excludes experiment batch drivers, generated
run outputs, and private scenario-generation corpora.

## Repository Layout

```text
OpenART/                         framework runtime, configs, Dockerfiles, docs, tests
OpenART/examples/tasks/          local smoke task and high-complexity examples
openart-tools/                   managed tool subset used by bundled examples
```

## Setup

Commands below assume the repository root as the starting directory.

```bash
cd OpenART
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD"
```

Build the base task image:

```bash
docker build -t openart/task-base:latest -f images/Dockerfile.task-base .
```

## Local Smoke Run

This verifies the container and evaluator path without model credentials.

```bash
python -m framework.cli run \
  --task examples/tasks/local-smoke \
  --target-config configs/target-configs/target.local-smoke.yaml \
  --eval-strategy deterministic \
  --skip-attacker \
  --run-id local-smoke \
  --output-dir outputs/local-smoke
```

## High-Complexity Task Run

The bundled generated tasks live under `OpenART/examples/tasks/`:

| Task | Workflow nodes | Workspace files | Distinct tools |
|------|----------------|-----------------|----------------|
| `high-complexity-kb-health` | 100 | 67 | 29 |
| `high-complexity-kb-integration` | 100 | 109 | 26 |
| `high-complexity-release-sync` | 100 | 134 | 32 |

Build the target image you want to evaluate. The default config uses OpenCode:

```bash
docker build -t openart/opencode:latest -f images/Dockerfile.opencode .
```

Copy `.env.example` to `.env` and fill in your model endpoint values:

```bash
cp .env.example .env
```

Run a high-complexity task without an attacker:

```bash
python -m framework.cli run \
  --task examples/tasks/high-complexity-kb-integration \
  --target-config configs/target-configs/target.yaml \
  --tool-store ../openart-tools \
  --eval-strategy deterministic \
  --skip-attacker \
  --run-id kb-integration-target-only \
  --output-dir outputs/kb-integration-target-only
```

Run the same task with the default OpenCode-compatible attacker:

```bash
python -m framework.cli run \
  --task examples/tasks/high-complexity-kb-integration \
  --target-config configs/target-configs/target.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --tool-store ../openart-tools \
  --eval-strategy both \
  --max-iterations 2 \
  --run-id kb-integration-attacked \
  --output-dir outputs/kb-integration-attacked
```

The task graph selects the required managed tools from `../openart-tools`.
Outputs are local artifacts under `OpenART/outputs/` and are ignored by git.

## Planner

The planner uses the existing module entrypoint. Build the planner image, set
the planner variables in `.env`, and generate one task from a checked-in seed:

```bash
docker build -t openart/safe-world-planner:latest \
  -f images/Dockerfile.safe-world-planner .

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

Generated planner outputs are local artifacts and are ignored by git.

## Documentation

Start with [`OpenART/docs/README.md`](OpenART/docs/README.md), then read
[`OpenART/docs/01_quickstart.md`](OpenART/docs/01_quickstart.md) for run
commands and [`OpenART/docs/12_planner_design_implementation_usage.md`](OpenART/docs/12_planner_design_implementation_usage.md)
for planner usage.

## License

OpenART is released under the AGPL-3.0 license. See [`LICENSE`](LICENSE).
