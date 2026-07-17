# OpenART Runtime

This directory contains the runnable OpenART framework. Run commands from this
directory with `PYTHONPATH=$PWD` and the existing module entrypoints.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export PYTHONPATH="$PWD"
```

Build the base image used by local tasks:

```bash
docker build -t openart/task-base:latest -f images/Dockerfile.task-base .
```

## Local Smoke Run

The local smoke target uses only Python inside the task container and does not
need model credentials.

```bash
python -m framework.cli run \
  --task examples/tasks/local-smoke \
  --target-config configs/target-configs/target.local-smoke.yaml \
  --eval-strategy deterministic \
  --skip-attacker \
  --run-id local-smoke \
  --output-dir outputs/local-smoke
```

## High-Complexity Example Run

The release includes three generated OpenART task bundles under
`examples/tasks/`:

```text
high-complexity-kb-health
high-complexity-kb-integration
high-complexity-release-sync
```

Build the default OpenCode target image, then configure model credentials in
`.env` from `.env.example`.

```bash
docker build -t openart/opencode:latest -f images/Dockerfile.opencode .
cp .env.example .env
```

Run one high-complexity task without an attacker:

```bash
python -m framework.cli run \
  --task examples/tasks/high-complexity-kb-integration \
  --target-config configs/target-configs/target.yaml \
  --tool-store ../openart-tools \
  --eval-strategy deterministic \
  --skip-attacker \
  --output-dir outputs/kb-integration-target-only
```

Run with the default attacker:

```bash
python -m framework.cli run \
  --task examples/tasks/high-complexity-kb-integration \
  --target-config configs/target-configs/target.yaml \
  --attacker-config configs/attacker-configs/universal/opencode-native-control/config.yaml \
  --tool-store ../openart-tools \
  --eval-strategy both \
  --max-iterations 2 \
  --output-dir outputs/kb-integration-attacked
```

Generated outputs under `outputs/` are local artifacts and are ignored by git.

## Planner

The planner uses the existing module entrypoint:

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

## Docs

The canonical documentation starts at [`docs/README.md`](docs/README.md).
